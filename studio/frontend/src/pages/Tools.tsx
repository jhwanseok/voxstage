import { Plus, PlugZap, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api, type Bot, type Tool } from "../api";
import { domainName } from "../copy";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import { fmt, parse } from "../lib/values";
import {
  Button, Disclosure, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Select, Sheet,
  StatusChip, useToast, WordsInput,
} from "../ui";

type KV = [string, string][];
interface RuleDraft { when: KV; kind: "return" | "error"; ret: KV; error: string; delay: string }
interface Draft {
  name: string; params: string[]; risky: boolean; verifies: boolean; requires: string; retry: string;
  rules: RuleDraft[]; def: RuleDraft | null; revision: number | null;
}

const kv = (o: Record<string, unknown> | undefined): KV => Object.entries(o ?? {}).map(([k, v]) => [k, fmt(v)]);
const unkv = (rows: KV) => Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), parse(v)]));
const empty = (): RuleDraft => ({ when: [], kind: "return", ret: [], error: "", delay: "" });

function ruleToDraft(r: any): RuleDraft {
  return { when: kv(r.when), kind: "error" in r ? "error" : "return", ret: kv(r.return), error: r.error ?? "",
           delay: r.delay_ms === undefined ? "" : String(r.delay_ms) };
}
function draftToRule(r: RuleDraft, withWhen: boolean) {
  const o: any = {};
  if (withWhen) o.when = unkv(r.when);
  if (r.kind === "return") o.return = unkv(r.ret); else o.error = r.error;
  if (r.delay.trim() !== "") o.delay_ms = Number(r.delay);
  return o;
}
function toDraft(t: Tool | null): Draft {
  const b = t?.body ?? {};
  return { name: t?.name ?? "", params: b.params ?? [], risky: !!b.risky, verifies: !!b.verifies, requires: b.requires ?? "",
           retry: String(b.retry ?? 0), rules: (b.rules ?? []).map(ruleToDraft), def: b.default ? ruleToDraft(b.default) : null,
           revision: t?.revision ?? null };
}
function toBody(d: Draft, prev: Record<string, any>) {
  const { params: _p, requires: _r, verifies: _v, risky: _k, retry: _t, rules: _u, default: _d, ...rest } = prev;
  const b: any = { ...rest, params: d.params };
  if (d.requires) b.requires = d.requires;
  if (d.verifies) b.verifies = true;
  if (d.risky) b.risky = true;
  if (d.retry !== "0") b.retry = Number(d.retry);
  b.rules = d.rules.map((r) => draftToRule(r, true));
  if (d.def) b.default = draftToRule(d.def, false);
  return b;
}

function KVEditor({ rows, onChange, add, label }: { rows: KV; onChange: (r: KV) => void; add: string; label: string }) {
  return (
    <div className="space-y-1.5">
      {rows.map(([k, v], i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_2rem] items-center gap-1.5">
          <Input aria-label={`${label} ${i + 1} 이름`} className="font-mono text-[13px]" value={k} placeholder="이름" onChange={(e) => onChange(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
          <Input aria-label={`${label} ${i + 1} 값`} className="font-mono text-[13px]" value={v} placeholder="값" onChange={(e) => onChange(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
          <IconButton label={`${label} ${i + 1} 지우기`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 size={14} /></IconButton>
        </div>
      ))}
      <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onChange([...rows, ["", ""]])}>{add}</Button>
    </div>
  );
}

function RuleEditor({ r, onChange, withWhen, title, onRemove }: { r: RuleDraft; onChange: (r: RuleDraft) => void; withWhen: boolean; title: string; onRemove: () => void }) {
  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <div className="flex items-center justify-between text-[13px] font-semibold text-ink">{title}<Button size="sm" variant="ghost" onClick={onRemove}>지우기</Button></div>
      {withWhen && <div><div className="mb-1 text-xs font-medium text-ink-2">이 값이 들어오면</div><KVEditor label={`${title} 조건`} rows={r.when} onChange={(when) => onChange({ ...r, when })} add="조건 추가" /></div>}
      <div className="grid grid-cols-2 gap-2">
        <Field label="응답"><Select value={r.kind} onChange={(e) => onChange({ ...r, kind: e.target.value as "return" | "error" })}><option value="return">값을 돌려줌</option><option value="error">오류를 냄</option></Select></Field>
        <Field label="지연" optional><Input type="number" className="num" value={r.delay} placeholder="ms" onChange={(e) => onChange({ ...r, delay: e.target.value })} /></Field>
      </div>
      {r.kind === "return"
        ? <KVEditor label={`${title} 응답`} rows={r.ret} onChange={(ret) => onChange({ ...r, ret })} add="응답 값 추가" />
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
        <span className="flex-1 truncate text-right text-[13px]" role="status">{err ? <span className="font-medium text-err-fg">{err}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}</span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || !d.name || !!nameErr} onClick={save}>저장</Button>
      </>}>
      <div className="space-y-6">
        <Notice tone="brand" title={`${domainName(bot.domain)}의 모든 상담봇이 함께 써요`}>여기서 바꾸면 같은 업종의 다른 언어 상담봇도 다시 검증해야 해요.</Notice>
        <Field label="이름" hint="시나리오의 API 호출 단계에서 이 이름으로 골라요." error={nameErr || null}>
          <Input data-autofocus={isNew || undefined} className="font-mono" value={d.name} disabled={!isNew} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field label="받는 값"><WordsInput label="받는 값" value={d.params} onChange={(v) => set("params", v)} placeholder="값 이름 입력 후 Enter" /></Field>
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
              <RuleEditor key={i} title={`규칙 ${i + 1}`} r={r} withWhen onChange={(x) => set("rules", d.rules.map((y, j) => (j === i ? x : y)))} onRemove={() => set("rules", d.rules.filter((_, j) => j !== i))} />
            ))}
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => set("rules", [...d.rules, empty()])}>규칙 추가</Button>
            {d.def ? <RuleEditor title="어느 규칙에도 안 맞을 때" r={d.def} withWhen={false} onChange={(x) => set("def", x)} onRemove={() => set("def", null)} />
              : <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => set("def", empty())}>기본 응답 추가</Button>}
          </div>
        </Disclosure>
      </div>
    </Sheet>
  );
}

export default function Tools({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: tools, error, loading, reload } = useFetch<Tool[]>(`/domains/${bot.domain}/tools`, [bot.shared_revision]);
  const [open, setOpen] = useState<string | "new" | null>(null);
  const list = tools ?? [];
  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="API 연결" count={tools ? list.length : undefined}
        description={`시나리오가 부르는 외부 API 목록이에요. ${domainName(bot.domain)}의 모든 상담봇이 함께 써요.`}
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
                  <div className="mt-0.5 truncate text-xs text-muted">{(t.body.params ?? []).length ? `받는 값: ${(t.body.params as string[]).join(", ")}` : "받는 값 없음"}</div>
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
