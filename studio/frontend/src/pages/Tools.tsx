import { Plus, PlugZap, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api, type Bot, type Tool } from "../api";
import { domainName, EXTRACTORS, RETURN_ONLY } from "../copy";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import { paramNames, paramSpec, specText } from "../lib/datatypes";
import {
  fmtValue, newSlot, paramSlots, paramsOut, parseValue, PARAM_TYPES, RETURN_TYPES, returnSlots, returnsOut, slotOf, slotProblem,
  slotProblems, valueProblem, type Slot,
} from "../lib/tools";
import {
  Button, Disclosure, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Select, Sheet,
  StatusChip, useToast, WordsInput,
} from "../ui";

type KV = [string, string][];
interface RuleDraft { when: KV; kind: "return" | "error"; ret: KV; error: string; delay: string }
interface Draft {
  name: string; params: Slot[]; returns: Slot[]; risky: boolean; verifies: boolean; requires: string; retry: string;
  rules: RuleDraft[]; def: RuleDraft | null; revision: number | null;
}

const typeName = (t: string) => EXTRACTORS[t] ?? RETURN_ONLY[t] ?? t;
const kv = (o: Record<string, unknown> | undefined, slots: Slot[]): KV => Object.entries(o ?? {}).map(([k, v]) => [k, fmtValue(slotOf(slots, k), v)]);
const unkv = (rows: KV, slots: Slot[]) => Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), parseValue(slotOf(slots, k.trim()), v)]));
const empty = (): RuleDraft => ({ when: [], kind: "return", ret: [], error: "", delay: "" });

function ruleToDraft(r: any, params: Slot[], returns: Slot[]): RuleDraft {
  return { when: kv(r.when, params), kind: "error" in r ? "error" : "return", ret: kv(r.return, returns), error: r.error ?? "",
           delay: r.delay_ms === undefined ? "" : String(r.delay_ms) };
}
function draftToRule(r: RuleDraft, withWhen: boolean, params: Slot[], returns: Slot[]) {
  const o: any = {};
  if (withWhen) o.when = unkv(r.when, params);
  if (r.kind === "return") o.return = unkv(r.ret, returns); else o.error = r.error;
  if (r.delay.trim() !== "") o.delay_ms = Number(r.delay);
  return o;
}
function toDraft(t: Tool | null): Draft {
  const b = t?.body ?? {};
  const params = paramSlots(b.params), returns = returnSlots(b.returns);
  return { name: t?.name ?? "", params, returns, risky: !!b.risky, verifies: !!b.verifies, requires: b.requires ?? "",
           retry: String(b.retry ?? 0), rules: (b.rules ?? []).map((r: any) => ruleToDraft(r, params, returns)),
           def: b.default ? ruleToDraft(b.default, params, returns) : null, revision: t?.revision ?? null };
}
function toBody(d: Draft, prev: Record<string, any>) {
  const { params: _p, returns: _n, requires: _r, verifies: _v, risky: _k, retry: _t, rules: _u, default: _d, ...rest } = prev;
  const b: any = { ...rest, params: paramsOut(d.params) };
  const returns = returnsOut(d.returns);
  if (returns) b.returns = returns;
  if (d.requires) b.requires = d.requires;
  if (d.verifies) b.verifies = true;
  if (d.risky) b.risky = true;
  if (d.retry !== "0") b.retry = Number(d.retry);
  b.rules = d.rules.map((r) => draftToRule(r, true, d.params, d.returns));
  if (d.def) b.default = draftToRule(d.def, false, d.params, d.returns);
  return b;
}

/** What stops a save beyond the rows themselves: a rule may name only declared params and response items, with values of
 *  their type (the engine checks the same when it loads the file, P6; its message is shown if this misses something). */
export function ruleProblems(d: Draft): string[] {
  const typed = d.params.some((p) => p.type);
  const pNames = d.params.map((p) => p.name.trim()).filter(Boolean);
  const rNames = d.returns.map((p) => p.name.trim()).filter(Boolean);
  const out: string[] = [];
  const rules = [...d.rules.map((r, i) => ({ r, title: `규칙 ${i + 1}` })), ...(d.def ? [{ r: d.def, title: "기본 응답" }] : [])];
  for (const { r, title } of rules) {
    if (typed) for (const [k, v] of r.when) {
      if (k.trim() && !pNames.includes(k.trim())) out.push(`${title}: ${k.trim()}은(는) 받는 속성에 없어요`);
      else { const p = valueProblem(slotOf(d.params, k.trim()), v); if (p) out.push(`${title}, ${k.trim()}: ${p}`); }
    }
    if (r.kind === "return" && rNames.length) for (const [k, v] of r.ret) {
      if (k.trim() && !rNames.includes(k.trim())) out.push(`${title}: ${k.trim()}은(는) 응답 항목에 없어요`);
      else { const p = valueProblem(slotOf(d.returns, k.trim()), v); if (p) out.push(`${title}, ${k.trim()}: ${p}`); }
    }
  }
  return out;
}

/** One attribute the API takes, or one item it answers with: name, 형식, and what the 형식 needs. */
function SlotsEditor({ kind, slots, onChange }: { kind: "params" | "returns"; slots: Slot[]; onChange: (s: Slot[]) => void }) {
  const label = kind === "params" ? "받는 속성" : "응답 항목";
  const types = kind === "params" ? PARAM_TYPES : RETURN_TYPES;
  const set = (i: number, v: Partial<Slot>) => onChange(slots.map((s, j) => (j === i ? { ...s, ...v } : s)));
  return (
    <div className="space-y-2">
      {slots.map((s, i) => {
        const problem = s.name || s.type ? slotProblem(slots, i, kind) : null;
        return (
          <div key={i} className="space-y-2 rounded-lg border border-line p-2.5">
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-1.5">
              <Input aria-label={`${label} ${i + 1} 이름`} className="font-mono text-[13px]" value={s.name} placeholder="이름 (영어)"
                onChange={(e) => set(i, { name: e.target.value.trim() })} />
              <Select aria-label={`${label} ${i + 1} 형식`} value={s.type} onChange={(e) => set(i, { type: e.target.value })}>
                {kind === "params" && <option value="">정하지 않음 (예전 방식)</option>}
                {types.map((t) => <option key={t} value={t}>{typeName(t)}</option>)}
              </Select>
              <IconButton label={`${label} ${i + 1} 지우기`} onClick={() => onChange(slots.filter((_, j) => j !== i))}><Trash2 size={14} /></IconButton>
            </div>
            {s.type === "digits" && (
              <div className="flex items-center gap-2 text-[13px] text-ink-2">
                <label htmlFor={`${kind}-len-${i}`} className="shrink-0 whitespace-nowrap">자릿수</label>
                <Input id={`${kind}-len-${i}`} type="number" min={1} inputMode="numeric" className="num h-8 w-24" value={s.length} placeholder="자유"
                  onChange={(e) => set(i, { length: e.target.value })} />
                <span className="text-xs text-muted">비워 두면 자릿수는 보지 않아요</span>
              </div>
            )}
            {s.type === "choice" && (
              <WordsInput label={`${label} ${i + 1} 보기`} value={s.choices} placeholder="보기 입력 후 Enter" onChange={(choices) => set(i, { choices })} />
            )}
            {kind === "params" && (
              <label className="flex items-center gap-2 text-[13px] text-ink-2">
                <input type="checkbox" className="h-4 w-4 accent-[var(--brand-500)]" checked={s.required} onChange={(e) => set(i, { required: e.target.checked })} />
                꼭 필요해요<span className="text-xs text-muted">끄면 연결하지 않아도 API를 부를 수 있어요</span>
              </label>
            )}
            {problem && <p className="text-xs font-medium text-err-fg">{problem}</p>}
          </div>
        );
      })}
      <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onChange([...slots, newSlot(kind === "params" && slots.some((s) => !s.type) && slots.length ? "" : "text")])}>{label} 추가</Button>
    </div>
  );
}

/** One cell of a rule row: a name from the declared ones (a free name only when nothing is declared) and a value that
 *  follows the declared type. */
function RuleRow({ names, slots, row, onChange, onRemove, label }: {
  names: string[]; slots: Slot[]; row: [string, string]; onChange: (r: [string, string]) => void; onRemove: () => void; label: string;
}) {
  const [k, v] = row;
  const slot = slotOf(slots, k.trim());
  const problem = valueProblem(slot, v);
  return (
    <div className="space-y-1">
      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-1.5">
        {names.length ? (
          <Select aria-label={`${label} 이름`} className="font-mono text-[13px]" value={k} onChange={(e) => onChange([e.target.value, v])}>
            <option value="">고르기</option>
            {k && !names.includes(k) && <option value={k}>{k} (없는 이름)</option>}
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </Select>
        ) : (
          <Input aria-label={`${label} 이름`} className="font-mono text-[13px]" value={k} placeholder="이름" onChange={(e) => onChange([e.target.value, v])} />
        )}
        {slot?.type === "choice" ? (
          <Select aria-label={`${label} 값`} value={v} onChange={(e) => onChange([k, e.target.value])}>
            <option value="">고르기</option>
            {v && !slot.choices.includes(v) && <option value={v}>{v} (보기에 없음)</option>}
            {slot.choices.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
        ) : slot?.type === "boolean" ? (
          <Select aria-label={`${label} 값`} value={v || "true"} onChange={(e) => onChange([k, e.target.value])}>
            <option value="true">예</option><option value="false">아니요</option>
          </Select>
        ) : (
          <Input aria-label={`${label} 값`} className="font-mono text-[13px]" value={v} placeholder="값"
            inputMode={slot && ["digits", "number"].includes(slot.type) ? "numeric" : undefined}
            maxLength={slot?.type === "digits" && slot.length ? Number(slot.length) : undefined}
            onChange={(e) => onChange([k, e.target.value])} />
        )}
        <IconButton label={`${label} 지우기`} onClick={onRemove}><Trash2 size={14} /></IconButton>
      </div>
      {problem && <p className="text-xs font-medium text-err-fg">{problem}</p>}
    </div>
  );
}

function KVEditor({ rows, onChange, add, label, names, slots }: {
  rows: KV; onChange: (r: KV) => void; add: string; label: string; names: string[]; slots: Slot[];
}) {
  return (
    <div className="space-y-1.5">
      {rows.map((row, i) => (
        <RuleRow key={i} label={`${label} ${i + 1}`} names={names} slots={slots} row={row}
          onChange={(r) => onChange(rows.map((x, j) => (j === i ? r : x)))} onRemove={() => onChange(rows.filter((_, j) => j !== i))} />
      ))}
      <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onChange([...rows, ["", ""]])}>{add}</Button>
    </div>
  );
}

function RuleEditor({ r, onChange, withWhen, title, onRemove, params, returns }: {
  r: RuleDraft; onChange: (r: RuleDraft) => void; withWhen: boolean; title: string; onRemove: () => void; params: Slot[]; returns: Slot[];
}) {
  const pNames = params.map((p) => p.name.trim()).filter(Boolean);
  const rNames = returns.map((p) => p.name.trim()).filter(Boolean);
  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <div className="flex items-center justify-between text-[13px] font-semibold text-ink">{title}<Button size="sm" variant="ghost" onClick={onRemove}>지우기</Button></div>
      {withWhen && (
        <div>
          <div className="mb-1 text-xs font-medium text-ink-2">이 속성이 이런 값으로 들어오면</div>
          <KVEditor label={`${title} 조건`} rows={r.when} names={pNames} slots={params} onChange={(when) => onChange({ ...r, when })} add="조건 추가" />
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Field label="응답"><Select value={r.kind} onChange={(e) => onChange({ ...r, kind: e.target.value as "return" | "error" })}><option value="return">항목을 돌려줌</option><option value="error">오류를 냄</option></Select></Field>
        <Field label="지연" optional><Input type="number" className="num" value={r.delay} placeholder="ms" onChange={(e) => onChange({ ...r, delay: e.target.value })} /></Field>
      </div>
      {r.kind === "return"
        ? <KVEditor label={`${title} 응답`} rows={r.ret} names={rNames} slots={returns} onChange={(ret) => onChange({ ...r, ret })} add="돌려줄 항목 추가" />
        : <Field label="오류 코드" hint="예: timeout, not_found"><Input className="font-mono text-[13px]" value={r.error} onChange={(e) => onChange({ ...r, error: e.target.value })} /></Field>}
    </div>
  );
}

function Editor({ bot, tool, names, onClose, onSaved }: { bot: Bot; tool: Tool | null; names: string[]; onClose: () => void; onSaved: () => void }) {
  const fresh = useMemo(() => toDraft(tool), [tool]);
  const [d, setD] = useState(fresh);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toast = useToast();
  const dirty = JSON.stringify(d) !== JSON.stringify(fresh);
  useUnsavedWarning(dirty);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const isNew = tool === null;
  const nameErr = isNew && d.name && (!/^[a-z_][a-z0-9_]*$/.test(d.name) ? "영문 소문자, 숫자, 밑줄만 써 주세요" : names.includes(d.name) ? "이미 있는 이름이에요" : null);
  const close = () => { if (!dirty || window.confirm("저장하지 않은 변경이 있어요. 버리고 닫을까요?")) onClose(); };
  const blocker = slotProblems(d.params, d.returns) ?? ruleProblems(d)[0] ?? null;
  const untyped = d.params.some((p) => p.name.trim() && !p.type);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      const body = { name: d.name.trim(), body: toBody(d, tool?.body ?? {}), revision: d.revision };
      const r: any = isNew ? await api.post(`/domains/${bot.domain}/tools`, body) : await api.put(`/domains/${bot.domain}/tools/${tool!.name}`, body);
      toast(`저장했어요. ${r.affects_bots.length}개 상담봇을 다시 검증해야 해요`); onSaved();
    } catch (e) { setErr(e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 닫고 다시 열어 주세요." : (e as Error).message); }
    finally { setBusy(false); }
  };
  const remove = async () => {
    if (!tool) return;
    try { await api.del(`/domains/${bot.domain}/tools/${tool.name}`); }
    catch (e) {
      const flows = e instanceof ApiError ? e.body?.detail?.flows : null;
      if (!flows || !window.confirm(`이 API를 부르는 시나리오가 있어요: ${flows.map((f: any) => `${f.bot} ${f.flow}`).join(", ")}. 그래도 지울까요?`)) return;
      await api.del(`/domains/${bot.domain}/tools/${tool.name}?force=true`);
    }
    toast("API를 지웠어요"); onSaved();
  };

  return (
    <Sheet open onClose={close} subtitle={isNew ? "새 API" : "API 수정"} title={d.name || "새 API"}
      footer={<>
        {!isNew && <Button variant="danger" icon={<Trash2 size={15} />} onClick={remove}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status" title={err || blocker || undefined}>
          {err ? <span className="font-medium text-err-fg">{err}</span> : blocker ? <span className="font-medium text-err-fg">{blocker}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}
        </span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || !d.name || !!nameErr || !!blocker} onClick={save}>저장</Button>
      </>}>
      <div className="space-y-6">
        <Notice tone="brand" title={`${domainName(bot.domain, bot.domain_title)}의 모든 상담봇이 함께 써요`}>여기서 바꾸면 같은 업종의 다른 언어 상담봇도 다시 검증해야 해요.</Notice>
        <Field label="이름" hint="시나리오의 API 호출 단계에서 이 이름으로 골라요." error={nameErr || null}>
          <Input data-autofocus={isNew || undefined} className="font-mono" value={d.name} disabled={!isNew} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <section aria-label="받는 속성" className="space-y-2">
          <div>
            <h3 className="text-sm font-medium text-ink">받는 속성</h3>
            <p className="mt-0.5 text-xs text-muted">API를 부를 때 시나리오가 넘겨 주는 속성이에요. 형식을 정하면 게시 전에 엔진이 알맞은 속성을 연결했는지 검사해요.</p>
          </div>
          <SlotsEditor kind="params" slots={d.params} onChange={(s) => set("params", s)} />
          {untyped && <p className="text-xs text-warn-fg">형식이 없는 속성이 있어요. 지금은 엔진이 연결된 속성의 형식을 검사하지 못해요.</p>}
        </section>
        <section aria-label="응답 항목" className="space-y-2">
          <div>
            <h3 className="text-sm font-medium text-ink">응답 항목</h3>
            <p className="mt-0.5 text-xs text-muted">API가 돌려주는 항목이에요. 정해 두면 시나리오가 이 항목을 다른 API에 넘길 수 있고, 아래 가짜 응답이 같은 이름과 형식을 따라요.</p>
          </div>
          <SlotsEditor kind="returns" slots={d.returns} onChange={(s) => set("returns", s)} />
        </section>
        <fieldset className="space-y-2.5">
          <legend className="mb-1 text-sm font-medium text-ink">성격</legend>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--brand-500)]" checked={d.risky} onChange={(e) => set("risky", e.target.checked)} />
            <span>되돌릴 수 없어요<span className="block text-xs text-muted">돈이 움직이는 일처럼요. 예/아니오 확인 뒤에만 부를 수 있고 다시 시도하지 않아요.</span></span></label>
          <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--brand-500)]" checked={d.verifies} onChange={(e) => set("verifies", e.target.checked)} />
            <span>본인 확인을 해요</span></label>
        </fieldset>
        <div className="grid grid-cols-2 gap-3">
          <Field label="본인 확인이 필요해요"><Select value={d.requires} onChange={(e) => set("requires", e.target.value)}><option value="">아니요</option><option value="verified">예</option></Select></Field>
          <Field label="응답이 늦으면"><Select value={d.retry} onChange={(e) => set("retry", e.target.value)} disabled={d.risky}><option value="0">다시 시도 안 함</option><option value="1">한 번 더 시도</option></Select></Field>
        </div>
        <Disclosure title="가짜 API 응답 규칙" summary={`규칙 ${d.rules.length}개${d.def ? ", 기본 응답 있음" : ""}`} defaultOpen={isNew}>
          <p className="mb-3 text-xs text-muted">평가와 미리 보기에서 쓰는 가짜 응답이에요. 위에서부터 처음 맞는 규칙을 써요.</p>
          <div className="space-y-3">
            {d.rules.map((r, i) => (
              <RuleEditor key={i} title={`규칙 ${i + 1}`} r={r} withWhen params={d.params} returns={d.returns}
                onChange={(x) => set("rules", d.rules.map((y, j) => (j === i ? x : y)))} onRemove={() => set("rules", d.rules.filter((_, j) => j !== i))} />
            ))}
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => set("rules", [...d.rules, empty()])}>규칙 추가</Button>
            {d.def ? <RuleEditor title="어느 규칙에도 안 맞을 때" r={d.def} withWhen={false} params={d.params} returns={d.returns} onChange={(x) => set("def", x)} onRemove={() => set("def", null)} />
              : <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => set("def", empty())}>기본 응답 추가</Button>}
          </div>
        </Disclosure>
      </div>
    </Sheet>
  );
}

/** "account_last4 (숫자 자리 4자리), amount (숫자)": what a row of the list says about the attributes it takes. */
export function paramSummary(body: Record<string, any>): string {
  return paramNames(body).map((p) => { const s = paramSpec(body, p); const t = specText(s); return `${p}${t ? ` (${t})` : ""}${s && body.params?.[p]?.required === false ? ", 선택" : ""}`; }).join(", ");
}

export default function Tools({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: tools, error, loading, reload } = useFetch<Tool[]>(`/domains/${bot.domain}/tools`, [bot.shared_revision]);
  const [open, setOpen] = useState<string | "new" | null>(null);
  const list = tools ?? [];
  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="API 연결" count={tools ? list.length : undefined}
        description={`시나리오가 부르는 외부 API 목록이에요. ${domainName(bot.domain, bot.domain_title)}의 모든 상담봇이 함께 써요.`}
        actions={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setOpen("new")}>API 추가</Button>} />
      {error && <ErrorState error={error} onRetry={reload} what="API 목록" />}
      {loading && <LoadingBlock rows={4} />}
      {tools && list.length === 0 && <EmptyState icon={<PlugZap size={20} />} title="연결된 API가 없어요" action={<Button variant="primary" onClick={() => setOpen("new")}>API 추가</Button>}>잔액 조회처럼 시나리오가 부를 API를 넣어 보세요.</EmptyState>}
      {list.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {list.map((t) => (
            <li key={t.name}>
              <button type="button" onClick={() => setOpen(t.name)} className="flex w-full items-center gap-4 px-5 py-3.5 text-left hover:bg-sunken/60">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm font-semibold text-ink">{t.name}</div>
                  <div className="mt-0.5 truncate text-xs text-muted">{paramNames(t.body).length ? `받는 속성: ${paramSummary(t.body)}` : "받는 속성 없음"}</div>
                  {Object.keys(t.body.returns ?? {}).length > 0 && <div className="truncate text-xs text-muted">응답 항목: {Object.keys(t.body.returns).join(", ")}</div>}
                </div>
                <div className="flex flex-wrap justify-end gap-1.5">
                  {t.body.risky && <StatusChip tone="err">되돌릴 수 없음</StatusChip>}
                  {t.body.requires && <StatusChip tone="warn">본인 확인 필요</StatusChip>}
                  {t.body.verifies && <StatusChip tone="brand">본인 확인</StatusChip>}
                  {t.body.retry ? <StatusChip tone="idle">재시도</StatusChip> : null}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && <Editor key={open} bot={bot} tool={open === "new" ? null : list.find((t) => t.name === open) ?? null} names={list.map((t) => t.name)}
        onClose={() => setOpen(null)} onSaved={() => { reload(); refresh(); setOpen(null); }} />}
    </main>
  );
}
