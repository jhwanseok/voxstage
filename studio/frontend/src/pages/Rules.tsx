import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type Bot } from "../api";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import {
  COMMAND_NAMES, pairProblem, RULE_KINDS, type PatternBody, type RuleKind, type RulesResponse, type RuleTest,
} from "../lib/wording";
import { paths } from "../paths";
import { Button, ErrorState, Field, IconButton, Input, LoadingBlock, PageHeader, StatusChip, useToast, WordsInput } from "../ui";
import { SaveBar } from "./SaveBar";

type Bodies = Record<RuleKind, Record<string, any>>;

/** A pattern without empty lists, as the engine file holds it. */
export function cleanPattern(p: PatternBody): PatternBody {
  const out: PatternBody = {};
  if (p.any_of?.length) out.any_of = p.any_of;
  const all = (p.all_of ?? []).filter((g) => (Array.isArray(g) ? g.length : !!g));
  if (all.length) out.all_of = all;
  if (p.none_of?.length) out.none_of = p.none_of;
  if (p.regex?.length) out.regex = p.regex;
  if (p.priority !== undefined) out.priority = p.priority;
  if (p.note) out.note = p.note;
  return out;
}

/** The four files as the server takes them: patterns without empty lists. */
export function bodiesForSend(d: Bodies): Bodies {
  return {
    ...d,
    commands: Object.fromEntries(Object.entries(d.commands).map(([n, p]) => [n, cleanPattern(p as PatternBody)])),
    corrections: { correction: cleanPattern(d.corrections.correction ?? {}) },
  };
}

export const patternEmpty = (p: PatternBody) => { const c = cleanPattern(p); return !c.any_of && !c.all_of && !c.regex; };

function PatternFields({ label, value, onChange }: { label: string; value: PatternBody; onChange: (p: PatternBody) => void }) {
  const groups: string[][] = (value.all_of ?? []).map((g) => (Array.isArray(g) ? g : [g]));
  return (
    <div className="grid gap-3">
      <Field label="이 중 한 단어라도 들으면" error={patternEmpty(value) ? "단어를 하나 이상 넣어 주세요." : null}>
        <WordsInput label={`${label}: 한 단어라도`} tone="ok" value={value.any_of ?? []} onChange={(v) => onChange({ ...value, any_of: v })} />
      </Field>
      {groups.map((g, i) => (
        <Field key={i} label={`반드시 포함 ${i + 1} (이 중 하나)`} aside={<Button type="button" size="sm" variant="ghost" onClick={() => onChange({ ...value, all_of: groups.filter((_, j) => j !== i) })}>지우기</Button>}>
          <WordsInput label={`${label}: 반드시 포함 ${i + 1}`} tone="ok" value={g} onChange={(v) => onChange({ ...value, all_of: groups.map((x, j) => (j === i ? v : x)) })} />
        </Field>
      ))}
      <div><Button type="button" size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onChange({ ...value, all_of: [...groups, []] })}>반드시 포함할 단어 줄 추가</Button></div>
      <Field label="들어 있으면 맞지 않음" optional>
        <WordsInput label={`${label}: 들어 있으면 맞지 않음`} tone="err" value={value.none_of ?? []} onChange={(v) => onChange({ ...value, none_of: v })} />
      </Field>
    </div>
  );
}

function Card({ title, description, children }: { title: string; description: ReactNode; children: ReactNode }) {
  return (
    <section className="grid gap-x-8 gap-y-3 border-t border-line py-6 first:border-t-0 first:pt-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>
      </div>
      <div className="grid gap-4">{children}</div>
    </section>
  );
}

const ANSWER = { yes: "예", no: "아니요", unclear: "알 수 없음" } as const;

/** Types a sentence and shows what the engine's matchers find in it, with the words on screen (not yet saved). */
function TestBox({ bot, bodies }: { bot: Bot; bodies: Bodies }) {
  const [text, setText] = useState("");
  const [res, setRes] = useState<RuleTest | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr("");
    try { setRes(await api.post<RuleTest>(`/bots/${bot.slug}/rules/test`, { text, bodies: bodiesForSend(bodies) })); }
    catch (e) { setRes(null); setErr(e instanceof ApiError && e.body?.detail?.problems ? e.body.detail.problems.map((p: any) => p.message).join(" ") : (e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <section aria-labelledby="test-h" className="rounded-2xl border border-line bg-surface p-6">
      <h2 id="test-h" className="text-[15px] font-semibold text-ink">말 넣어 보기</h2>
      <p className="mt-0.5 text-[13px] text-muted">고객이 할 만한 말을 넣으면 엔진이 어떤 규칙을 찾는지 보여 줘요. 저장하지 않은 단어로도 해 볼 수 있어요.</p>
      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) void run(); }}>
        <Input aria-label="시험할 말" value={text} onChange={(e) => setText(e.target.value)} placeholder="예: 그냥 취소할게요" />
        <Button type="submit" loading={busy} disabled={!text.trim()}>확인</Button>
      </form>
      {err && <p className="mt-3 text-sm font-medium text-err-fg" role="alert">{err}</p>}
      {res && (
        <dl className="mt-4 grid gap-3 text-sm" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2"><dt className="w-28 text-muted">엔진이 읽은 말</dt><dd className="text-ink-2">{res.tokens.join(" · ") || "(남은 말 없음)"}</dd></div>
          <div className="flex flex-wrap items-center gap-2"><dt className="w-28 text-muted">명령어</dt>
            <dd>{res.command.matched ? <StatusChip tone="brand">{COMMAND_NAMES[res.command.matched] ?? res.command.matched}</StatusChip> : <span className="text-ink-2">해당 없음</span>}</dd></div>
          <div className="flex flex-wrap items-center gap-2"><dt className="w-28 text-muted">확인 질문의 답</dt>
            <dd className="flex items-center gap-2"><StatusChip tone={res.confirm.answer === "unclear" ? "idle" : res.confirm.answer === "yes" ? "ok" : "err"}>{ANSWER[res.confirm.answer]}</StatusChip>
              <span className="text-xs text-muted">{[...res.confirm.yes_words.map((w) => `예: ${w}`), ...res.confirm.no_words.map((w) => `아니요: ${w}`)].join(", ")}</span></dd></div>
          <div className="flex flex-wrap items-center gap-2"><dt className="w-28 text-muted">값을 고치는 말</dt>
            <dd>{res.correction.matched ? <StatusChip tone="warn">고치는 말로 봐요</StatusChip> : <span className="text-ink-2">해당 없음</span>}</dd></div>
          <div className="flex flex-wrap items-center gap-2"><dt className="w-28 text-muted">헷갈리는 숫자</dt>
            <dd className="text-ink-2">{res.confusions.length ? res.confusions.map((c) => `${c.value} ↔ ${c.partner}`).join(", ") : "해당 없음"}</dd></div>
        </dl>
      )}
    </section>
  );
}

export default function Rules({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const toast = useToast();
  const { data, error, loading, reload, setData } = useFetch<RulesResponse>(`/bots/${bot.slug}/rules`);
  const initial = useMemo<Bodies | null>(() => data && (Object.fromEntries(RULE_KINDS.map((k) => [k, data.kinds[k].body ?? {}])) as Bodies), [data]);
  const [d, setD] = useState<Bodies | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  useEffect(() => setD(initial), [initial]);
  const changed = d && initial ? RULE_KINDS.filter((k) => JSON.stringify(d[k]) !== JSON.stringify(initial[k])) : [];
  const dirty = changed.length > 0;
  useUnsavedWarning(dirty);

  if (error) return <main className="mx-auto max-w-5xl px-8 py-8"><ErrorState error={error} onRetry={reload} what="응답 규칙" /></main>;
  if (loading || !data || !d || !initial) return <main className="mx-auto max-w-5xl px-8 py-8"><LoadingBlock rows={5} /></main>;

  const set = <K extends RuleKind>(k: K, v: Record<string, any>) => setD({ ...d, [k]: v });
  const yes: string[] = d.confirm.yes_words ?? [];
  const no: string[] = d.confirm.no_words ?? [];
  const both = yes.filter((w) => no.includes(w));
  const pairs: [number, number][] = d.confusions.pairs ?? [];
  const pairErr = pairProblem(pairs);
  const commandsBad = ["cancel", "back", "agent"].some((c) => patternEmpty(d.commands[c] ?? {}));
  const invalid = !yes.length || !no.length || both.length > 0 || commandsBad || patternEmpty(d.corrections.correction ?? {}) || !!pairErr;

  const save = async () => {
    setBusy(true); setSaveError("");
    let latest = data;
    try {
      for (const k of changed) {
        const body = bodiesForSend(d)[k];
        latest = await api.put<RulesResponse>(`/bots/${bot.slug}/rules/${k}`, { body, revision: latest.kinds[k].revision });
      }
      setData(latest); refresh();
      toast("저장했어요. 검증하고 게시하면 엔진에 반영돼요");
    } catch (e) {
      setData(latest);
      setSaveError(e instanceof ApiError && e.status === 422 && e.body?.detail?.problems ? e.body.detail.problems.map((p: any) => p.message).join(" ")
        : e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 새로 불러온 뒤 다시 고쳐 주세요." : (e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="응답 규칙" description="고객의 짧은 말을 어떻게 알아들을지 정하는 단어예요. 말투가 언어마다 달라서 상담봇마다 따로 둬요." />
      <div className="space-y-6">
        <form onSubmit={(ev) => { ev.preventDefault(); if (!invalid && dirty) void save(); }} className="rounded-2xl border border-line bg-surface">
          <div className="px-6 py-6">
            <Card title="예, 아니요 단어" description="위험한 일을 하기 전 '진행할까요?' 하고 물었을 때 답을 알아듣는 단어예요. 키패드는 1이 예, 2가 아니요예요.">
              <Field label="예라고 알아듣는 단어" error={!yes.length ? "단어를 하나 이상 넣어 주세요." : null}>
                <WordsInput label="예 단어" tone="ok" value={yes} onChange={(v) => set("confirm", { ...d.confirm, yes_words: v })} />
              </Field>
              <Field label="아니요라고 알아듣는 단어" error={!no.length ? "단어를 하나 이상 넣어 주세요." : both.length ? `예와 아니요에 모두 있는 단어가 있어요: ${both.join(", ")}` : null}>
                <WordsInput label="아니요 단어" tone="err" value={no} onChange={(v) => set("confirm", { ...d.confirm, no_words: v })} />
              </Field>
            </Card>
            <Card title="명령어" description="통화 중 언제 말해도 가장 먼저 알아듣는 말이에요. 취소하면 처음 상태로 돌아가요.">
              {(["cancel", "back", "agent"] as const).map((c) => (
                <div key={c} className="rounded-xl border border-line p-4">
                  <div className="mb-3 text-sm font-semibold text-ink">{COMMAND_NAMES[c]}</div>
                  <PatternFields label={COMMAND_NAMES[c]} value={d.commands[c] ?? {}} onChange={(p) => set("commands", { ...d.commands, [c]: p })} />
                </div>
              ))}
            </Card>
            <Card title="값을 고치는 말" description="방금 읽어 드린 값이 틀렸다고 고객이 말할 때 알아듣는 단어예요. 예: 아니요, 잘못 들었어요.">
              <PatternFields label="값을 고치는 말" value={d.corrections.correction ?? {}} onChange={(p) => set("corrections", { correction: p })} />
            </Card>
            <Card title="헷갈리는 숫자" description="인식기가 자주 헷갈리는 숫자 쌍이에요. 고객이 '아니요'만 말하면 짝이 되는 숫자를 대신 읽어 보며 물어봐요. (예: 13과 30)">
              <ul className="grid gap-2">
                {pairs.map((p, i) => (
                  <li key={i} className="flex items-center gap-2">
                    {[0, 1].map((j) => (
                      <Input key={j} type="number" aria-label={`${i + 1}번째 쌍의 ${j + 1}번째 숫자`} className="num w-28" value={Number.isNaN(p[j]) ? "" : p[j]}
                        onChange={(e) => set("confusions", { pairs: pairs.map((q, k) => (k === i ? (j === 0 ? [e.target.value === "" ? NaN : Number(e.target.value), q[1]] : [q[0], e.target.value === "" ? NaN : Number(e.target.value)]) : q)) })} />
                    ))}
                    <IconButton label={`${i + 1}번째 쌍 지우기`} onClick={() => set("confusions", { pairs: pairs.filter((_, k) => k !== i) })}><Trash2 size={15} /></IconButton>
                  </li>
                ))}
              </ul>
              {pairErr && <p className="text-xs font-medium text-err-fg">{pairErr}</p>}
              <div><Button type="button" size="sm" icon={<Plus size={14} />} onClick={() => set("confusions", { pairs: [...pairs, [NaN, NaN]] })}>쌍 추가</Button></div>
            </Card>
          </div>
          <SaveBar dirty={dirty} busy={busy} invalid={invalid} error={saveError} note="저장 후 검증과 게시가 필요해요" onReset={() => { setD(initial); setSaveError(""); }} />
        </form>
        <TestBox bot={bot} bodies={d} />
        <p className="text-xs text-muted">고객에게 읽어 주는 문구는 <Link className="font-semibold text-brand-700 hover:underline" to={paths.bot(bot.slug, "notices")}>안내 문구</Link>에서 고쳐요.</p>
      </div>
    </main>
  );
}
