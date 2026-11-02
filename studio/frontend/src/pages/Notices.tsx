import { ArrowDown, ArrowUp, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type Bot } from "../api";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import {
  freshId, insertName, move, NOTICE_ID, noticeTextProblem, valueProblem, type ExpressionCheck, type NoticeItem,
  type NoticesResponse, type Problem,
} from "../lib/wording";
import { paths } from "../paths";
import { Button, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Segmented, Tag, Textarea, useToast } from "../ui";
import { SaveBar } from "./SaveBar";

type Draft = { notices: NoticeItem[]; wording: Record<string, string> };
type Tab = "fixed" | "wording";

/** The server's field messages by field name: `wording.readback`, `notices.<id>.text`, ... */
const problemMap = (ps: Problem[]) => Object.fromEntries(ps.map((p) => [p.field, p.message]));

/** Live check of an `applies_when` text with the engine, for the text that was typed last. */
function useExpressionCheck(slug: string, text: string) {
  const [res, setRes] = useState<ExpressionCheck | null>(null);
  useEffect(() => {
    if (!text.trim()) { setRes(null); return; }
    let alive = true;
    const t = setTimeout(() => {
      api.post<ExpressionCheck>(`/bots/${slug}/notices/check-expression`, { text }).then((r) => alive && setRes(r)).catch(() => alive && setRes(null));
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [slug, text]);
  return res;
}

function FixedRow({ bot, n, i, last, data, error, onChange, onMove, onRemove }: {
  bot: Bot; n: NoticeItem; i: number; last: boolean; data: NoticesResponse; error: Record<string, string>;
  onChange: (p: Partial<NoticeItem>) => void; onMove: (by: -1 | 1) => void; onRemove: () => void;
}) {
  const when = n.applies_when ?? "";
  const check = useExpressionCheck(bot.slug, when);
  const used = data.used_by[n.id] ?? [];
  const textErr = noticeTextProblem(n.text) ?? error[`notices.${n.id}.text`] ?? null;
  const whenErr = (check && !check.ok ? check.error : null) ?? error[`notices.${n.id}.applies_when`] ?? null;
  const idErr = !NOTICE_ID.test(n.id) ? "영문자로 시작하고 영문자, 숫자, _, -만 쓸 수 있어요." : error[`notices.${n.id}.id`] ?? null;
  return (
    <li className="rounded-xl border border-line bg-surface p-5" aria-label={`고정 안내 ${i + 1}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="num grid h-6 w-6 place-items-center rounded-full bg-sunken text-xs font-semibold text-ink-2">{i + 1}</span>
        <code className="text-[13px] text-ink-2">{n.id}</code>
        {data.to_translate.includes(n.id) && <Tag tone="warn">번역할 곳</Tag>}
        {used.length > 0 ? <Tag tone="brand">쓰는 시나리오 {used.join(", ")}</Tag> : <Tag>쓰는 시나리오 없음</Tag>}
        <span className="flex-1" />
        <IconButton label="위로" disabled={i === 0} onClick={() => onMove(-1)}><ArrowUp size={15} /></IconButton>
        <IconButton label="아래로" disabled={last} onClick={() => onMove(1)}><ArrowDown size={15} /></IconButton>
        <IconButton label="지우기" onClick={onRemove}><Trash2 size={15} /></IconButton>
      </div>
      <div className="grid gap-4">
        <Field label="이름" hint="시나리오의 '고정 안내' 단계가 이 이름으로 불러요." error={idErr}>
          <Input value={n.id} onChange={(e) => onChange({ id: e.target.value })} disabled={used.length > 0} />
        </Field>
        <Field label="읽어 줄 문구" hint="적은 그대로 읽어요." error={textErr}>
          <Textarea rows={3} value={n.text} onChange={(e) => onChange({ text: e.target.value })} />
        </Field>
        <Field label="말하는 조건" optional error={whenErr}
          hint={when.trim() ? (check?.ok ? `엔진이 읽을 수 있어요. 쓰는 속성: ${check.names.join(", ") || "없음"}` : "확인하는 중…") : "비워 두면 항상 말해요. 속성 값으로 조건을 줄 수 있어요. 예: amount > 1000000"}>
          <Input value={when} placeholder="예: customer.grade == 'gold'" onChange={(e) => onChange({ applies_when: e.target.value || null })} />
        </Field>
        <div className="-mt-2 flex flex-wrap items-center gap-1.5" aria-label="조건에 쓸 수 있는 속성">
          <span className="text-xs text-muted">눌러서 넣기:</span>
          {[...data.reserved, ...data.attributes].map((a) => (
            <button key={a} type="button" onClick={() => onChange({ applies_when: insertName(when, a) })}
              className="rounded-md bg-sunken px-2 py-0.5 text-xs text-ink-2 hover:bg-brand-50 hover:text-brand-700">{a}</button>
          ))}
        </div>
      </div>
    </li>
  );
}

export default function Notices({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const toast = useToast();
  const { data, error, loading, reload, setData } = useFetch<NoticesResponse>(`/bots/${bot.slug}/notices`);
  const [tab, setTab] = useState<Tab>("fixed");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [server, setServer] = useState<Record<string, string>>({});
  const initial = useMemo<Draft | null>(() => (data ? { notices: data.notices, wording: data.wording } : null), [data]);
  useEffect(() => { setDraft(initial); setServer({}); }, [initial]);
  const dirty = !!draft && !!initial && JSON.stringify(draft) !== JSON.stringify(initial);
  useUnsavedWarning(dirty);

  if (error) return <main className="mx-auto max-w-5xl px-8 py-8"><ErrorState error={error} onRetry={reload} what="안내 문구" /></main>;
  if (loading || !data || !draft || !initial) return <main className="mx-auto max-w-5xl px-8 py-8"><LoadingBlock rows={5} /></main>;

  const ids = draft.notices.map((n) => n.id);
  const dupId = (id: string) => ids.filter((x) => x === id).length > 1;
  const wordingBad = Object.entries(draft.wording).filter(([k, t]) => valueProblem(k, t, data.placeholder_keys));
  const fixedBad = draft.notices.some((n) => noticeTextProblem(n.text) || !NOTICE_ID.test(n.id) || dupId(n.id));
  const invalid = wordingBad.length > 0 || fixedBad;
  const setNotice = (i: number, p: Partial<NoticeItem>) => setDraft({ ...draft, notices: draft.notices.map((n, j) => (j === i ? { ...n, ...p } : n)) });

  const save = async () => {
    setBusy(true); setSaveError(""); setServer({});
    try {
      const out = await api.put<NoticesResponse>(`/bots/${bot.slug}/notices`, { ...draft, revision: data.revision });
      setData(out); refresh();
      toast("저장했어요. 검증하고 게시하면 엔진이 새 문구로 말해요");
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.body?.detail?.problems) {
        setServer(problemMap(e.body.detail.problems));
        setSaveError("엔진이 받아들이지 않는 곳이 있어요. 표시된 곳을 고쳐 주세요.");
      } else setSaveError(e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 새로 불러온 뒤 다시 고쳐 주세요." : (e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="안내 문구" description="고객에게 읽어 주는 문구예요. 고정 안내는 적은 그대로 읽고, 상황별 문구는 엔진이 정해진 상황에서 말해요." />
      {data.to_translate.length > 0 && (
        <div className="mb-4"><Notice tone="warn" title={`번역할 고정 안내가 ${data.to_translate.length}개 남았어요`}>
          다른 언어 상담봇에서 복사한 문구예요. 문구를 고쳐 저장하면 번역한 것으로 봐요.
        </Notice></div>
      )}
      <form onSubmit={(ev) => { ev.preventDefault(); if (!invalid && dirty) void save(); }} className="rounded-2xl border border-line bg-surface">
        <div className="border-b border-line px-6 py-4">
          <Segmented<Tab> label="안내 문구 종류" value={tab} onChange={setTab}
            options={[{ value: "fixed", label: "고정 안내", count: draft.notices.length }, { value: "wording", label: "상황별 문구", count: 17 }]} />
        </div>
        <div className="px-6 py-6">
          {tab === "fixed" ? (
            <div className="space-y-4">
              <p className="text-[13px] text-muted">시나리오의 '고정 안내' 단계에서 위에서부터 차례로, 조건이 맞는 것만 빠짐없이 읽어요. 순서는 위아래 버튼으로 바꿔요. 저장하면 우선순위가 10, 20, 30…으로 다시 매겨져요.</p>
              {draft.notices.length === 0 ? (
                <EmptyState title="고정 안내가 없어요" action={<Button type="button" icon={<Plus size={14} />} onClick={() => setDraft({ ...draft, notices: [{ id: freshId(ids), text: "", applies_when: null }] })}>고정 안내 추가</Button>}>
                  금융 상품 고지처럼 한 글자도 바꾸지 않고 읽어야 하는 문구를 여기에 둬요.
                </EmptyState>
              ) : (
                <ul className="space-y-3">
                  {draft.notices.map((n, i) => (
                    <FixedRow key={i} bot={bot} n={n} i={i} last={i === draft.notices.length - 1} data={data}
                      error={{ ...server, ...(dupId(n.id) ? { [`notices.${n.id}.id`]: "같은 이름이 이미 있어요." } : {}) }}
                      onChange={(p) => setNotice(i, p)} onMove={(by) => setDraft({ ...draft, notices: move(draft.notices, i, by) })}
                      onRemove={() => { if (window.confirm(`고정 안내 '${n.id}'를 지울까요? 이 이름을 쓰는 시나리오는 검증에서 고칠 곳으로 나와요.`)) setDraft({ ...draft, notices: draft.notices.filter((_, j) => j !== i) }); }} />
                  ))}
                </ul>
              )}
              {draft.notices.length > 0 && (
                <Button type="button" icon={<Plus size={14} />} onClick={() => setDraft({ ...draft, notices: [...draft.notices, { id: freshId(ids), text: "", applies_when: null }] })}>고정 안내 추가</Button>
              )}
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <p className="min-w-0 flex-1 text-[13px] text-muted">엔진이 정해진 상황에서 말하는 문구예요. 상황 17가지는 정해져 있어서 문구만 고칠 수 있어요. <code>{"{value}"}</code>는 값이 들어갈 자리예요.</p>
                <Button type="button" icon={<RotateCcw size={14} />} onClick={() => { if (window.confirm("17개 문구를 모두 기본 문구로 되돌릴까요?")) setDraft({ ...draft, wording: { ...data.starter_wording } }); }}>모두 기본 문구로</Button>
              </div>
              <ul className="space-y-4">
                {Object.keys(draft.wording).map((key) => {
                  const text = draft.wording[key];
                  const err = valueProblem(key, text, data.placeholder_keys) ?? server[`wording.${key}`] ?? null;
                  const starter = data.starter_wording[key];
                  return (
                    <li key={key} className="grid gap-x-6 gap-y-2 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
                      <div>
                        <div className="text-sm font-semibold text-ink">{data.meaning[key] ?? key}</div>
                        <code className="text-xs text-muted">{key}</code>
                      </div>
                      <Field label={<span className="sr-only">{key} 문구</span>} error={err}
                        aside={text !== starter ? <button type="button" className="text-xs font-semibold text-brand-700 hover:underline" onClick={() => setDraft({ ...draft, wording: { ...draft.wording, [key]: starter } })}>기본 문구로 되돌리기</button> : undefined}>
                        <Textarea rows={2} value={text} onChange={(e) => setDraft({ ...draft, wording: { ...draft.wording, [key]: e.target.value } })} />
                      </Field>
                    </li>
                  );
                })}
              </ul>
              <p className="text-xs text-muted">바꾼 문구를 직접 들어 보려면 위의 <b>대화로 테스트</b>를 쓰세요. 고객 말을 알아듣는 단어는 <Link className="font-semibold text-brand-700 hover:underline" to={paths.bot(bot.slug, "rules")}>응답 규칙</Link>에서 고쳐요.</p>
            </div>
          )}
        </div>
        <SaveBar dirty={dirty} busy={busy} invalid={invalid} error={saveError} note="저장 후 검증과 게시가 필요해요" onReset={() => { setDraft(initial); setServer({}); setSaveError(""); }} />
      </form>
    </main>
  );
}
