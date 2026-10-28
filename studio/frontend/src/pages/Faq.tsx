import { BookOpenText, Plus, Search, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api, type Bot, type Faq, type Report } from "../api";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import { MIN_ASR, MIN_PARAPHRASES, needsAttention, problems, readPattern, toBody, toDraft, toPattern, type FaqDraft } from "../lib/faq";
import {
  Button, cn, Disclosure, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Segmented,
  Sheet, StatusChip, Tag, Textarea, useToast, WordsInput,
} from "../ui";

type Filter = "all" | "changed" | "attention";

/** Sentences, one per row: edit in place, delete, or add at the bottom with Enter. */
function SentenceList({ items, onChange, label, placeholder }: { items: string[]; onChange: (v: string[]) => void; label: string; placeholder: string }) {
  const [text, setText] = useState("");
  const add = () => { const t = text.trim(); if (t && !items.includes(t)) onChange([...items, t]); setText(""); };
  return (
    <div className="space-y-1.5">
      {items.map((t, i) => (
        <div key={i} className="flex items-center gap-1">
          <Input aria-label={`${label} ${i + 1}`} value={t} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} />
          <IconButton label={`${label} ${i + 1} 지우기`} onClick={() => onChange(items.filter((_, j) => j !== i))}><Trash2 size={15} /></IconButton>
        </div>
      ))}
      <div className="flex items-center gap-1">
        <Input aria-label={`${label} 추가`} value={text} placeholder={placeholder} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={add} disabled={!text.trim()}>추가</Button>
      </div>
    </div>
  );
}

function Count({ n, min }: { n: number; min: number }) {
  return <span className={cn("num text-xs font-medium", n < min ? "text-err-fg" : "text-muted")}>{n}개{n < min && `, ${min}개 이상 필요`}</span>;
}

function Editor({ bot, entry, ids, onClose, onSaved }: {
  bot: Bot; entry: Faq | null; ids: string[]; onClose: () => void; onSaved: (id: string | null) => void;
}) {
  const isNew = entry === null;
  const fresh = useMemo(() => {
    let n = ids.length + 1;
    while (ids.includes(`${bot.domain}.faq.new_${n}`)) n += 1;
    return toDraft(entry, `${bot.domain}.faq.new_${n}`);
  }, [entry, ids, bot.domain]);
  const [d, setD] = useState<FaqDraft>(fresh);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toast = useToast();
  const dirty = JSON.stringify(d) !== JSON.stringify(fresh);
  useUnsavedWarning(dirty);
  const set = <K extends keyof FaqDraft>(k: K, v: FaqDraft[K]) => setD((x) => ({ ...x, [k]: v }));
  const probs = problems(d, ids, isNew);
  const err = (f: string) => (tried ? probs.find((p) => p.field === f)?.text ?? null : null);
  // only missing words/sentences block a save; counts below the guidance are saved and flagged in the list
  const blocking = probs.filter((p) => ["id", "question", "answer"].includes(p.field));

  const close = useCallback(() => {
    if (dirty && !window.confirm("저장하지 않은 변경이 있어요. 버리고 닫을까요?")) return;
    onClose();
  }, [dirty, onClose]);

  const save = async () => {
    setTried(true); setError("");
    if (blocking.length) return;
    setBusy(true);
    try {
      const body = toBody(d);
      if (isNew) await api.post(`/bots/${bot.slug}/faq`, body); else await api.put(`/bots/${bot.slug}/faq/${entry!.id}`, body);
      toast(probs.length ? "저장했어요. 아직 채울 곳이 있어요" : "저장했어요", probs.length ? "warn" : "ok");
      onSaved(body.id);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 닫고 다시 열어 주세요." : (e as Error).message);
    } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!entry || !window.confirm(`"${entry.question}" 질문을 지울까요? 게시하기 전까지는 엔진에 남아 있어요.`)) return;
    await api.del(`/bots/${bot.slug}/faq/${entry.id}`);
    toast("질문을 지웠어요"); onSaved(null);
  };

  const pattern = toPattern(d);
  const groupLabel = (i: number) => `반드시 포함 ${i + 1}`;
  return (
    <Sheet open onClose={close} subtitle={isNew ? "새 질문" : "질문 수정"} title={d.question.trim() || "새 질문"}
      footer={<>
        {!isNew && <Button variant="danger" icon={<Trash2 size={15} />} onClick={remove}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status">
          {error ? <span className="font-medium text-err-fg">{error}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}
        </span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty} onClick={save}>저장</Button>
      </>}>
      <div className="space-y-6">
        {tried && blocking.length > 0 && <Notice tone="err" title="채워야 저장할 수 있어요">{blocking.map((p) => p.text).join(", ")}</Notice>}

        <div className="space-y-4">
          <Field label="고객이 묻는 말" error={err("question")}>
            <Input data-autofocus value={d.question} onChange={(e) => set("question", e.target.value)} placeholder="예: 영업시간이 어떻게 되나요?" />
          </Field>
          <Field label="봇의 답변" hint="적힌 그대로 읽어 드려요. 짧은 문장 두세 개가 듣기 좋아요." error={err("answer")}>
            <Textarea rows={3} value={d.answer} onChange={(e) => set("answer", e.target.value)} />
          </Field>
        </div>

        <Disclosure defaultOpen={isNew || !pattern.all_of?.length} title="알아듣는 조건" summary={readPattern(pattern)}
          badge={err("pattern") ? <StatusChip tone="err">필요</StatusChip> : null}>
          <p className="mb-3 text-xs text-muted">고객 말에 아래 조건이 모두 맞으면 이 답변을 해요.</p>
          <div className="space-y-3">
            {d.allOf.map((g, i) => (
              <div key={i}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[13px] font-medium text-ink">{groupLabel(i)} <span className="font-normal text-muted">이 중 한 단어 이상</span></span>
                  <Button size="sm" variant="ghost" onClick={() => set("allOf", d.allOf.filter((_, j) => j !== i))}>줄 지우기</Button>
                </div>
                <WordsInput label={groupLabel(i)} tone="brand" value={g} onChange={(v) => set("allOf", d.allOf.map((x, j) => (j === i ? v : x)))} />
              </div>
            ))}
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => set("allOf", [...d.allOf, []])}>반드시 포함할 단어 줄 추가</Button>
            <div>
              <div className="mb-1 text-[13px] font-medium text-ink">이 중 하나라도 포함 <span className="font-normal text-muted">선택</span></div>
              <WordsInput label="이 중 하나라도 포함" value={d.anyOf} onChange={(v) => set("anyOf", v)} />
            </div>
            <div>
              <div className="mb-1 text-[13px] font-medium text-ink">들어 있으면 제외 <span className="font-normal text-muted">다른 질문과 헷갈릴 때</span></div>
              <WordsInput label="들어 있으면 제외" tone="err" value={d.noneOf} onChange={(v) => set("noneOf", v)} />
            </div>
          </div>
          <p className="mt-4 rounded-lg bg-sunken px-3 py-2 text-[13px] text-ink-2" aria-live="polite">{readPattern(pattern)}</p>
          <div className="mt-3">
            <Disclosure title="고급" summary={d.priority || d.regex.length ? `우선순위 ${d.priority || "없음"}, 정규식 ${d.regex.length}개` : "우선순위와 정규식"}>
              <div className="space-y-4">
                <Field label="우선순위" optional hint="두 질문이 함께 맞을 때 숫자가 큰 쪽이 이겨요.">
                  <Input type="number" className="num w-32" value={d.priority} onChange={(e) => set("priority", e.target.value)} />
                </Field>
                <div>
                  <div className="mb-1.5 text-sm font-medium text-ink">정규식 <span className="text-xs font-normal text-muted">단어 조건으로 말할 수 없을 때만</span></div>
                  <SentenceList label="정규식" items={d.regex} onChange={(v) => set("regex", v)} placeholder="예: 몇\s*시" />
                </div>
              </div>
            </Disclosure>
          </div>
        </Disclosure>

        <Disclosure defaultOpen={d.paraphrases.length < MIN_PARAPHRASES} title="같은 뜻의 다른 말"
          badge={<Count n={d.paraphrases.length} min={MIN_PARAPHRASES} />} summary={d.paraphrases.slice(0, 2).join(" / ")}>
          <p className="mb-3 text-xs text-muted">고객이 실제로 할 법한 말이에요. 조건을 만들 때 이 문장들이 모두 맞는지 같이 보세요.</p>
          <SentenceList label="다른 말" items={d.paraphrases} onChange={(v) => set("paraphrases", v)} placeholder="예: 은행 몇 시에 문 닫아요" />
        </Disclosure>

        <Disclosure defaultOpen={d.asr.length < MIN_ASR} title="잘못 알아들은 예시" badge={<Count n={d.asr.length} min={MIN_ASR} />}
          summary={d.asr.slice(0, 2).join(" / ")}>
          <p className="mb-3 text-xs text-muted">음성 인식이 틀리게 받아 적은 문장이에요. 이런 말도 알아듣는지 확인할 때 써요.</p>
          <SentenceList label="잘못 알아들은 예시" items={d.asr} onChange={(v) => set("asr", v)} placeholder="예: 영업 시간이 어떻게 되나 요" />
        </Disclosure>

        <Disclosure title="개발 정보" summary={d.id}>
          <Field label="질문 이름" hint={isNew ? "파일과 평가 데이터에서 이 질문을 가리키는 이름이에요. 저장한 뒤에는 바꿀 수 없어요." : "저장한 뒤에는 바꿀 수 없어요."} error={err("id")}>
            <Input value={d.id} disabled={!isNew} onChange={(e) => set("id", e.target.value)} className="font-mono text-[13px]" />
          </Field>
        </Disclosure>
      </div>
    </Sheet>
  );
}

function stateChip(e: Faq) {
  if (needsAttention(e)) return <StatusChip tone="err">확인 필요</StatusChip>;
  if (e.published === "new") return <StatusChip tone="warn">새 질문</StatusChip>;
  if (e.published === "changed") return <StatusChip tone="warn">고침</StatusChip>;
  if (e.published === "same") return <span className="text-xs text-muted">게시됨</span>;
  return <span className="text-xs text-muted">게시 전</span>;
}

export default function FaqPage({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: list, error, loading, reload } = useFetch<Faq[]>(`/bots/${bot.slug}/faq`);
  const { data: report } = useFetch<Report | null>(`/bots/${bot.slug}/validation`, [bot.draft_revision, bot.validated]);
  const [open, setOpen] = useState<string | "new" | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  useEffect(() => { setOpen(null); }, [bot.slug]);

  const all = list ?? [];
  const changed = all.filter((e) => e.published === "changed" || e.published === "new");
  const attention = all.filter(needsAttention);
  const shown = (filter === "changed" ? changed : filter === "attention" ? attention : all)
    .filter((e) => !q || `${e.question} ${e.answer} ${(e.paraphrases ?? []).join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  const engineItems = (report?.items ?? []).filter((i) => /faq/.test(i.file) && i.severity === "error");
  const published = all.some((e) => e.published);

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <PageHeader title="자주 묻는 질문" count={list ? all.length : undefined}
        description="고객이 묻는 말과 봇의 답변이에요. 줄을 누르면 고칠 수 있어요."
        actions={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setOpen("new")}>질문 추가</Button>} />
      {engineItems.length > 0 && (
        <div className="mb-4"><Notice tone="err" title="엔진이 질문 파일을 받아들이지 않아요">{engineItems.map((i) => i.message).join(" ")}</Notice></div>
      )}
      {error && <ErrorState error={error} onRetry={reload} what="질문 목록" />}
      {loading && <LoadingBlock rows={6} label="질문을 불러오는 중" />}
      {list && all.length === 0 && (
        <EmptyState icon={<BookOpenText size={20} />} title="아직 질문이 없어요"
          action={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setOpen("new")}>첫 질문 추가</Button>}>
          고객이 자주 묻는 말과 답변을 넣어 보세요.
        </EmptyState>
      )}
      {list && all.length > 0 && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Segmented label="보기 기준" value={filter} onChange={setFilter} options={[
              { value: "all", label: "전체", count: all.length },
              ...(published ? [{ value: "changed" as const, label: "게시 후 고친 질문", count: changed.length }] : []),
              { value: "attention", label: "확인이 필요한 질문", count: attention.length },
            ]} />
            <span className="flex-1" />
            <div className="relative w-72 max-w-full">
              <Search size={15} className="pointer-events-none absolute left-3 top-2.5 text-muted" aria-hidden />
              <Input aria-label="질문 검색" className="pl-9" placeholder="질문, 답변, 다른 말에서 찾기" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
          </div>
          <div className="overflow-hidden rounded-xl border border-line bg-surface">
            <table className="w-full text-sm">
              <thead className="bg-sunken text-left text-xs font-medium text-muted">
                <tr><th scope="col" className="px-4 py-2.5">질문과 답변</th><th scope="col" className="w-[30%] px-4 py-2.5 max-md:hidden">알아듣는 단어</th><th scope="col" className="w-28 px-4 py-2.5">상태</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {shown.map((e) => {
                  const words = (e.pattern?.all_of ?? []).flatMap((g: any) => (Array.isArray(g) ? g.slice(0, 2) : [g])).slice(0, 4);
                  return (
                    <tr key={e.id} onClick={() => setOpen(e.id)}
                      className={cn("cursor-pointer align-top hover:bg-sunken/60 focus-within:bg-brand-50", open === e.id && "bg-brand-50")}>
                      <td className="px-4 py-3">
                        <button type="button" onClick={(ev) => { ev.stopPropagation(); setOpen(e.id); }}
                          className="text-left font-medium text-ink outline-offset-4">{e.question}<span className="sr-only"> 고치기</span></button>
                        <div className="mt-0.5 line-clamp-1 text-[13px] text-muted">{e.answer}</div>
                      </td>
                      <td className="px-4 py-3 max-md:hidden"><div className="flex flex-wrap gap-1">{words.map((w: string) => <Tag key={w}>{w}</Tag>)}</div></td>
                      <td className="whitespace-nowrap px-4 py-3">{stateChip(e)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {shown.length === 0 && <p className="px-4 py-10 text-center text-sm text-muted">조건에 맞는 질문이 없어요. 검색어나 보기 기준을 바꿔 보세요.</p>}
          </div>
        </>
      )}
      {open && (
        <Editor key={open} bot={bot} entry={open === "new" ? null : all.find((e) => e.id === open) ?? null}
          ids={all.map((e) => e.id)} onClose={() => setOpen(null)}
          onSaved={() => { reload(); refresh(); setOpen(null); }} />
      )}
    </main>
  );
}
