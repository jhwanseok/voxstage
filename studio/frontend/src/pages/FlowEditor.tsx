import {
  applyNodeChanges, Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider, useReactFlow,
  type Connection, type Edge, type Node, type NodeChange, type NodeProps,
} from "@xyflow/react";
import {
  ArrowLeft, CircleStop, CornerDownRight, GitFork, HelpCircle, LayoutGrid, ListChecks, ListOrdered, Megaphone,
  MessageSquare, PlugZap, Plus, Rocket, Save, ShieldAlert, ShieldCheck, Trash2, Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useBotActions } from "../actions";
import { ApiError, api, type Bot, type FlowDetail, type Item, type Report, type Tool } from "../api";
import { EXTRACTORS, ON_EXCEED } from "../copy";
import { paramNames } from "../lib/datatypes";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import { autoLayout, START_ID } from "../lib/graph";
import {
  addNode, connect, edges as draftEdges, exits, KINDS, localProblems, removeNode, renameNode, VALID_ID, type FlowDraft, type Kind,
} from "../lib/flowEdit";
import type { TypesDoc, TypesResponse } from "../lib/datatypes";
import { paths } from "../paths";
import { AskTarget, BindingForm, cardNote, RoleDefaultField, RolesSection } from "./FlowData";
import {
  Button, cn, Disclosure, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, Select, StatusChip, Textarea, useToast,
  WordsInput,
} from "../ui";

// --- what each kind of step looks like ---

const KIND: Record<Kind, { label: string; hint: string; icon: typeof MessageSquare; bar: string; soft: string }> = {
  say: { label: "말하기", hint: "정해진 문장을 읽어요", icon: MessageSquare, bar: "bg-sky-500", soft: "bg-sky-50 text-sky-800 dark:bg-sky-950 dark:text-sky-200" },
  ask: { label: "묻기", hint: "질문하고 답에서 값을 받아요", icon: HelpCircle, bar: "bg-amber-500", soft: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200" },
  confirm: { label: "예/아니오 확인", hint: "진행할지 확인해요", icon: ListChecks, bar: "bg-pink-500", soft: "bg-pink-50 text-pink-800 dark:bg-pink-950 dark:text-pink-200" },
  call: { label: "API 호출", hint: "연결된 API를 불러요", icon: PlugZap, bar: "bg-emerald-500", soft: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" },
  branch: { label: "조건으로 나누기", hint: "값에 따라 다른 길로 가요", icon: GitFork, bar: "bg-violet-500", soft: "bg-violet-50 text-violet-800 dark:bg-violet-950 dark:text-violet-200" },
  notices: { label: "안내 문구", hint: "꼭 알려야 할 문구를 읽어요", icon: Megaphone, bar: "bg-cyan-500", soft: "bg-cyan-50 text-cyan-800 dark:bg-cyan-950 dark:text-cyan-200" },
  form: { label: "여러 값 묻기", hint: "빈 값만 차례로 물어요", icon: ListOrdered, bar: "bg-orange-500", soft: "bg-orange-50 text-orange-800 dark:bg-orange-950 dark:text-orange-200" },
  goto: { label: "이동", hint: "다른 단계로 건너뛰어요", icon: CornerDownRight, bar: "bg-slate-400", soft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" },
  end: { label: "끝내기", hint: "시나리오를 마쳐요", icon: CircleStop, bar: "bg-slate-600", soft: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" },
};
const WAITS = new Set(["ask", "form", "confirm"]);
const CARD_W = 280;

/** The name inside `{amount | money('USD')}`; a longer expression reads as "값" (the whole one is in the tooltip). */
function placeholder(part: string): string {
  const name = part.slice(1, -1).split("|")[0].trim();
  return /^[A-Za-z_][\w.]*$/.test(name) ? name : "값";
}

/** `{amount}` placeholders tinted, so the spoken sentence still reads as one sentence. */
function Spoken({ text }: { text: string }) {
  if (!text) return <span className="italic text-muted">문장을 적어 주세요</span>;
  return <>{text.split(/(\{[^{}]*\})/).map((part, i) => part.startsWith("{") && part.endsWith("}")
    ? <span key={i} className="rounded bg-brand-50 px-0.5 font-medium text-brand-700" title={part}>{placeholder(part)}</span>
    : <span key={i}>{part}</span>)}</>;
}

function headline(b: Record<string, any>, tools: Map<string, Tool>): ReactNode {
  switch (b.type as Kind) {
    case "say": return <Spoken text={b.text ?? ""} />;
    case "ask": case "confirm": return <Spoken text={b.prompt ?? ""} />;
    case "call": return b.tool ? <>{b.tool}{tools.get(b.tool)?.body.risky && " 실행"}</> : <span className="italic text-muted">API를 골라 주세요</span>;
    case "branch": return `조건 ${(b.cases ?? []).length}개로 나뉘어요`;
    case "notices": return b.ids?.length ? `안내 ${b.ids.length}개를 읽어요` : "해당하는 안내를 모두 읽어요";
    case "form": return `${(b.slots ?? []).length}가지 값을 차례로 물어요`;
    case "goto": return b.next ? `${b.next} 단계로 가요` : "갈 곳을 골라 주세요";
    case "end": return b.action === "handoff" ? "상담사에게 연결하며 끝내요" : b.action === "end_call" ? "통화를 끝내요" : "시나리오를 마쳐요";
    default: return b.type;
  }
}

interface CardData extends Record<string, unknown> { nid: string; body: Record<string, any>; tools: Map<string, Tool>; engine: number; local: number; isStart: boolean; note: string | null }

function StepCard({ data, selected }: NodeProps<Node<CardData>>) {
  if (!data.body) return null;
  const k = KIND[data.body.type as Kind] ?? KIND.goto;
  const Icon = k.icon;
  const risky = data.body.type === "call" && data.tools.get(data.body.tool)?.body.risky;
  const ex = exits(data.body);
  return (
    <div style={{ width: CARD_W }} className={cn("overflow-hidden rounded-xl bg-surface shadow-sm ring-1",
      selected ? "ring-2 ring-brand-500" : data.engine ? "ring-err-fg" : "ring-line")}>
      <Handle type="target" position={Position.Top} id="in" />
      <div className={cn("h-1.5", k.bar)} />
      <div className="px-4 pb-3 pt-2.5">
        <div className="flex items-center gap-1.5">
          <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold", k.soft)}><Icon size={13} aria-hidden />{k.label}</span>
          <span className="flex-1" />
          {WAITS.has(data.body.type) && <span className="rounded bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-2">답을 기다려요</span>}
          {risky && <span className="inline-flex items-center gap-0.5 rounded bg-err-bg px-1.5 py-0.5 text-[11px] font-semibold text-err-fg"><ShieldAlert size={11} aria-hidden />되돌릴 수 없음</span>}
        </div>
        <div className="mt-2 line-clamp-3 text-[14px] font-semibold leading-snug text-ink">{headline(data.body, data.tools)}</div>
        {data.note && <div className={cn("mt-1 text-xs", data.note.startsWith("연결 안 된") ? "font-medium text-warn-fg" : "text-ink-2")}>{data.note}</div>}
        {(data.engine > 0 || data.local > 0) && (
          <div className={cn("mt-1.5 text-xs font-medium", data.engine ? "text-err-fg" : "text-warn-fg")}>
            {data.engine ? `엔진 검사 문제 ${data.engine}개` : `확인할 곳 ${data.local}개`}
          </div>
        )}
      </div>
      {ex.length > 0 && (
        <div className="flex justify-around border-t border-line px-1 pb-1.5 pt-1">
          {ex.map((e) => (
            <div key={e.handle} className={cn("relative px-2 py-0.5 text-xs font-semibold", e.target ? "text-ink-2" : "text-muted")}>
              {e.label}<Handle type="source" position={Position.Bottom} id={e.handle} style={{ bottom: -8 }} aria-label={`${e.label} 연결`} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface TriggerData extends Record<string, unknown> { header: Record<string, any>; hasStart: boolean }
function TriggerCard({ data, selected }: NodeProps<Node<TriggerData>>) {
  const t = data.header.triggers ?? {};
  const inc: string[] = [...(t.any_of ?? []), ...(t.all_of ?? []).map((g: any) => (Array.isArray(g) ? g.join("/") : g))];
  const exc: string[] = t.none_of ?? [];
  const role = data.header.role === "verification";
  return (
    <div style={{ width: CARD_W }} className={cn("overflow-hidden rounded-xl bg-surface shadow-sm ring-1", selected ? "ring-2 ring-brand-500" : "ring-brand-500/40")}>
      <div className="h-1.5 bg-brand-500" />
      <div className="px-4 pb-3 pt-2.5">
        <span className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-1.5 py-0.5 text-xs font-semibold text-brand-700"><Zap size={13} aria-hidden />{role ? "다른 시나리오가 부르면 시작해요" : "이런 말을 들으면 시작해요"}</span>
        {!role && (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
              <span className="font-semibold text-ok-fg">포함</span>
              {inc.length ? inc.slice(0, 6).map((w) => <span key={w} className="rounded-md bg-ok-bg px-1.5 py-0.5 font-medium text-ok-fg">{w}</span>) : <span className="text-muted">아직 없어요</span>}
              {inc.length > 6 && <span className="text-muted">외 {inc.length - 6}</span>}
            </div>
            {exc.length > 0 && (
              <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                <span className="font-semibold text-err-fg">제외</span>
                {exc.slice(0, 5).map((w) => <span key={w} className="rounded-md bg-err-bg px-1.5 py-0.5 font-medium text-err-fg">{w}</span>)}
                {exc.length > 5 && <span className="text-muted">외 {exc.length - 5}</span>}
              </div>
            )}
            {(data.header.buttons ?? []).length > 0 && <div className="mt-1 text-xs text-muted">버튼 {(data.header.buttons as string[]).join(", ")}</div>}
          </>
        )}
      </div>
      <div className={cn("relative border-t border-line py-1 text-center text-xs font-semibold", data.hasStart ? "text-ink-2" : "text-err-fg")}>
        {data.hasStart ? "첫 단계로" : "첫 단계를 이어 주세요"}
        <Handle type="source" position={Position.Bottom} id="next" style={{ bottom: -8 }} aria-label="첫 단계 연결" />
      </div>
    </div>
  );
}
const nodeTypes = { step: StepCard, trigger: TriggerCard };

// --- side panel forms ---

function targetOptions(d: FlowDraft, self: string) {
  return d.order.filter((id) => id !== self).map((id) => {
    const b = d.nodes[id];
    const k = KIND[b.type as Kind]?.label ?? b.type;
    const text = String(b.text ?? b.prompt ?? b.tool ?? "").replace(/\{[^}]*\}/g, "…").slice(0, 24);
    return { id, label: `${k}${text ? `: ${text}` : ""} (${id})` };
  });
}

function TargetSelect({ d, self, value, onChange, label }: { d: FlowDraft; self: string; value: string | null; onChange: (v: string | null) => void; label: string }) {
  const opts = targetOptions(d, self);
  const missing = value && !d.nodes[value];
  return (
    <Field label={label} error={missing ? `${value} 단계가 없어요` : null}>
      <Select value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">이어지지 않음</option>
        {missing && <option value={value!}>{value} (없음)</option>}
        {opts.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </Select>
    </Field>
  );
}

function PairsEditor({ rows, onChange, left, right }: { rows: [string, string][]; onChange: (r: [string, string][]) => void; left: string; right: string }) {
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[1fr_1fr_2rem] gap-1.5 text-xs text-muted"><span>{left}</span><span>{right}</span></div>
      {rows.map(([a, b], i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_2rem] items-center gap-1.5">
          <Input aria-label={`${left} ${i + 1}`} value={a} onChange={(e) => onChange(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
          <Input aria-label={`${right} ${i + 1}`} value={b} onChange={(e) => onChange(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
          <IconButton label={`${i + 1}번째 줄 지우기`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 size={14} /></IconButton>
        </div>
      ))}
      <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onChange([...rows, ["", ""]])}>줄 추가</Button>
    </div>
  );
}

const TEMPLATE_HINT = "중괄호로 감싼 이름(예: {amount})은 앞에서 받은 값으로 바뀌어요.";

function NodeForm({ d, id, tools, doc, lang, problems, onPatch, onNode, onConnect, onRemove, onRename, onMakeStart }: {
  d: FlowDraft; id: string; tools: Tool[]; doc: TypesDoc | null; lang: string; problems: { text: string; engine: boolean }[];
  onNode: (body: Record<string, any>) => void;
  onPatch: (patch: Record<string, any>, drop?: string[]) => void; onConnect: (handle: string, to: string | null) => void;
  onRemove: () => void; onRename: (to: string) => void; onMakeStart: () => void;
}) {
  const b = d.nodes[id];
  const k = KIND[b.type as Kind] ?? KIND.goto;
  const Icon = k.icon;
  const [rename, setRename] = useState(id);
  useEffect(() => setRename(id), [id]);
  const tool = tools.find((t) => t.name === b.tool);
  const set = (key: string) => (v: any) => (v === "" || v === null || v === undefined ? onPatch({}, [key]) : onPatch({ [key]: v }));

  return (
    <div className="space-y-5 p-5">
      <div className="flex items-start gap-2">
        <span className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold", k.soft)}><Icon size={13} aria-hidden />{k.label}</span>
        <span className="text-xs text-muted">{k.hint}</span>
        <span className="flex-1" />
        {d.start === id ? <StatusChip tone="brand" icon={false}>첫 단계</StatusChip> : <Button size="sm" variant="ghost" onClick={onMakeStart}>첫 단계로</Button>}
      </div>
      {problems.length > 0 && (
        <ul className="space-y-1.5">{problems.map((p, i) => (
          <li key={i}><Notice tone={p.engine ? "err" : "warn"} title={p.engine ? "엔진 검사" : "저장 전 확인"}>{p.text}</Notice></li>
        ))}</ul>
      )}

      {b.type === "say" && <Field label="읽을 문장" hint={TEMPLATE_HINT}><Textarea rows={4} value={b.text ?? ""} onChange={(e) => onPatch({ text: e.target.value })} /></Field>}

      {(b.type === "ask" || b.type === "confirm") && (
        <Field label="고객에게 하는 말" hint={TEMPLATE_HINT}><Textarea rows={3} value={b.prompt ?? ""} onChange={(e) => onPatch({ prompt: e.target.value })} /></Field>
      )}
      {b.type === "confirm" && <RoleDefaultField d={d} lang={lang} doc={doc} b={b} onPatch={onPatch} />}
      {b.type === "confirm" && <p className="rounded-lg bg-sunken px-3 py-2 text-xs text-ink-2">고객은 예/아니오로 답하거나 키패드 1, 2를 눌러요. 되돌릴 수 없는 API는 이 단계의 "예" 다음에만 부를 수 있어요.</p>}

      {b.type === "ask" && <AskTarget d={d} doc={doc} lang={lang} b={b} onPatch={onPatch} />}
      {b.type === "ask" && !b.role && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field label="받은 값의 이름" hint="문장에서 {이름}으로 써요.">
              <Input className="font-mono text-[13px]" value={b.slot ?? ""} onChange={(e) => onPatch({ slot: e.target.value })} />
            </Field>
            <Field label="받는 값의 종류">
              <Select value={b.extractor ?? "text"} onChange={(e) => onPatch({ extractor: e.target.value }, e.target.value === "digits" ? ["choices"] : e.target.value === "choice" ? ["length"] : ["length", "choices"])}>
                {Object.entries(EXTRACTORS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
          </div>
          {b.extractor === "digits" && (
            <Field label="자릿수" optional hint="비우면 길이를 따지지 않아요.">
              <Input type="number" className="num w-28" value={b.length ?? ""} onChange={(e) => set("length")(e.target.value === "" ? "" : Number(e.target.value))} />
            </Field>
          )}
        </>
      )}
      {b.type === "ask" && (
        <>
          {b.extractor === "choice" && (
            <div>
              <div className="mb-1.5 text-sm font-medium text-ink">보기</div>
              <PairsEditor left="고객이 하는 말" right="저장할 값" rows={Object.entries(b.choices ?? {}).map(([a, v]) => [a, String(v)])}
                onChange={(rows) => onPatch({ choices: Object.fromEntries(rows.filter(([a]) => a.trim())) })} />
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" className="h-4 w-4 accent-[var(--brand-500)]" checked={b.interruptible !== false}
              onChange={(e) => (e.target.checked ? onPatch({}, ["interruptible"]) : onPatch({ interruptible: false }))} />
            묻는 중에 다른 문의를 받을 수 있어요
          </label>
        </>
      )}

      {b.type === "call" && (
        <>
          <Field label="부를 API">
            <Select value={b.tool ?? ""} onChange={(e) => {
              // keep what is bound for params the new API also takes; the rest shows as "연결 안 됨"
              const keep = new Set(paramNames(tools.find((t) => t.name === e.target.value)?.body));
              const pick = (o: Record<string, any> | undefined) => Object.fromEntries(Object.entries(o ?? {}).filter(([p]) => keep.has(p)));
              const args = pick(b.args), bind = pick(b.bind);
              onPatch({ tool: e.target.value, ...(Object.keys(args).length ? { args } : {}), ...(Object.keys(bind).length ? { bind } : {}) },
                [...(Object.keys(args).length ? [] : ["args"]), ...(Object.keys(bind).length ? [] : ["bind"])]);
            }}>
              <option value="">고르기</option>
              {tools.map((t) => <option key={t.name} value={t.name}>{t.name}{t.body.risky ? " (되돌릴 수 없음)" : ""}</option>)}
            </Select>
          </Field>
          {tool?.body.risky && <Notice tone="warn" title="되돌릴 수 없는 API예요">예/아니오 확인 단계의 "예"에서만 이어질 수 있어요. 엔진이 게시 전에 검사해요.</Notice>}
          {tool && <BindingForm d={d} id={id} tool={tool} tools={tools} doc={doc} lang={lang} onNode={onNode} />}
        </>
      )}

      {b.type === "branch" && (
        <div className="space-y-3">
          {(b.cases ?? []).map((c: any, i: number) => (
            <div key={i} className="rounded-lg border border-line p-3">
              <div className="mb-2 flex items-center justify-between text-[13px] font-semibold text-ink">조건 {i + 1}
                <Button size="sm" variant="ghost" onClick={() => onPatch({ cases: (b.cases ?? []).filter((_: any, j: number) => j !== i) })}>지우기</Button>
              </div>
              <Field label="이럴 때" hint="예: result.status == 'active'">
                <Input className="font-mono text-[13px]" value={c.when ?? ""} onChange={(e) => onPatch({ cases: b.cases.map((x: any, j: number) => (j === i ? { ...x, when: e.target.value } : x)) })} />
              </Field>
              <div className="mt-3"><TargetSelect d={d} self={id} label="갈 곳" value={c.next ?? null} onChange={(v) => onConnect(`case-${i}`, v)} /></div>
            </div>
          ))}
          <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => onPatch({ cases: [...(b.cases ?? []), { when: "", next: null }] })}>조건 추가</Button>
        </div>
      )}

      {b.type === "notices" && (
        <Field label="읽을 안내" optional hint="비우면 이 상황에 해당하는 안내를 모두 읽어요.">
          <WordsInput label="읽을 안내" value={b.ids ?? []} onChange={(v) => (v.length ? onPatch({ ids: v }) : onPatch({}, ["ids"]))} />
        </Field>
      )}

      {b.type === "form" && (
        <div className="space-y-3">
          {(b.slots ?? []).map((s: any, i: number) => (
            <Field key={i} label={<>{i + 1}. <code className="text-[13px]">{s.slot}</code> <span className="font-normal text-muted">{EXTRACTORS[s.extractor] ?? s.extractor}</span></>}>
              <Input value={s.prompt ?? ""} onChange={(e) => onPatch({ slots: b.slots.map((x: any, j: number) => (j === i ? { ...x, prompt: e.target.value } : x)) })} />
            </Field>
          ))}
          <p className="text-xs text-muted">값의 종류와 미리 말할 문장은 개발 정보에서 볼 수 있어요.</p>
        </div>
      )}

      {b.type === "end" && (
        <>
          <Field label="끝낸 뒤">
            <Select value={b.action ?? ""} onChange={(e) => (e.target.value ? onPatch({ action: e.target.value }, e.target.value === "handoff" ? [] : ["reason"]) : onPatch({}, ["action", "reason"]))}>
              <option value="">대화를 이어 가요</option>
              <option value="handoff">{ON_EXCEED.handoff}</option>
              <option value="end_call">{ON_EXCEED.end_call}</option>
            </Select>
          </Field>
          {b.action === "handoff" && (
            <Field label="연결 이유" optional hint="상담사 화면에 남는 짧은 영문 코드예요.">
              <Input className="font-mono text-[13px]" value={b.reason ?? ""} onChange={(e) => set("reason")(e.target.value)} />
            </Field>
          )}
        </>
      )}

      {exits(b).filter((e) => !e.handle.startsWith("case-")).length > 0 && (
        <div className="space-y-3 border-t border-line pt-4">
          <div className="text-sm font-semibold text-ink">이어지는 곳</div>
          {exits(b).filter((e) => !e.handle.startsWith("case-")).map((e) => (
            <TargetSelect key={e.handle} d={d} self={id} label={e.handle === "next" ? "다음 단계" : e.handle === "else" ? "어느 조건에도 안 맞으면" : `${e.label}일 때`}
              value={e.target} onChange={(v) => onConnect(e.handle, v)} />
          ))}
          <p className="text-xs text-muted">캔버스에서 카드 아래의 점을 끌어 다른 카드에 놓아도 이어져요.</p>
        </div>
      )}

      <Disclosure title="개발 정보" summary={id}>
        <div className="space-y-3">
          <Field label="단계 이름" hint="파일과 엔진 메시지에서 이 단계를 가리켜요. 바꾸면 이어진 곳도 함께 바뀌어요."
            error={rename !== id && (!VALID_ID.test(rename) || d.nodes[rename]) ? "영문, 숫자, 밑줄만 쓰고 겹치지 않게 해 주세요" : null}>
            <div className="flex gap-2">
              <Input className="font-mono text-[13px]" value={rename} onChange={(e) => setRename(e.target.value)} />
              <Button disabled={rename === id || !VALID_ID.test(rename) || !!d.nodes[rename]} onClick={() => onRename(rename)}>바꾸기</Button>
            </div>
          </Field>
          <pre className="max-h-48 overflow-auto rounded-lg bg-sunken p-3 text-xs text-ink-2">{JSON.stringify(b, null, 2)}</pre>
        </div>
      </Disclosure>

      <Button variant="danger" icon={<Trash2 size={15} />} onClick={onRemove}>이 단계 지우기</Button>
    </div>
  );
}

function FlowSettings({ bot, flowId, d, doc, onHeader, setDraft, onAddDefaultStep, onDeleted }: {
  bot: Bot; flowId: string; d: FlowDraft; doc: TypesDoc | null; onHeader: (h: Record<string, any>) => void;
  setDraft: (f: (x: FlowDraft) => FlowDraft) => void; onAddDefaultStep: (role: string) => void; onDeleted: () => void;
}) {
  const h = d.header;
  const t = h.triggers ?? {};
  const setT = (patch: Record<string, any>) => {
    const next = { ...t, ...patch };
    Object.keys(next).forEach((k) => (next[k] === undefined || (Array.isArray(next[k]) && !next[k].length && k !== "any_of")) && delete next[k]);
    onHeader({ ...h, triggers: next });
  };
  const groups: string[][] = (t.all_of ?? []).map((g: any) => (Array.isArray(g) ? g : [g]));
  const rest = Object.fromEntries(Object.entries(h).filter(([k]) => !["triggers", "buttons", "role", "roles"].includes(k)));
  return (
    <div className="space-y-5 p-5">
      <RolesSection bot={bot} d={d} doc={doc} setDraft={setDraft} onAddDefaultStep={onAddDefaultStep} />
      <div className="border-t border-line" />
      {h.role === "verification" ? (
        <Notice tone="brand" title="본인 확인 시나리오예요">고객의 말로 시작하지 않고, 본인 확인이 필요한 시나리오가 부를 때 시작해요.</Notice>
      ) : (
        <>
          <div>
            <div className="text-sm font-semibold text-ink">시작하는 말</div>
            <p className="mt-0.5 text-xs text-muted">고객 말이 아래 조건에 맞으면 이 시나리오를 시작해요.</p>
          </div>
          <Field label="이 중 한 단어라도 들으면"><WordsInput label="이 중 한 단어라도 들으면" tone="ok" value={t.any_of ?? []} onChange={(v) => setT({ any_of: v })} /></Field>
          {groups.map((g, i) => (
            <Field key={i} label={`반드시 포함 ${i + 1}`} aside={<Button size="sm" variant="ghost" onClick={() => setT({ all_of: groups.filter((_, j) => j !== i) })}>지우기</Button>}>
              <WordsInput label={`반드시 포함 ${i + 1}`} tone="ok" value={g} onChange={(v) => setT({ all_of: groups.map((x, j) => (j === i ? v : x)) })} />
            </Field>
          ))}
          <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => setT({ all_of: [...groups, []] })}>반드시 포함할 단어 줄 추가</Button>
          <Field label="들어 있으면 시작하지 않음"><WordsInput label="들어 있으면 시작하지 않음" tone="err" value={t.none_of ?? []} onChange={(v) => setT({ none_of: v })} /></Field>
          <Field label="우선순위" optional hint="두 시나리오가 함께 맞을 때 숫자가 큰 쪽이 시작해요.">
            <Input type="number" className="num w-28" value={t.priority ?? ""} onChange={(e) => setT({ priority: e.target.value === "" ? undefined : Number(e.target.value) })} />
          </Field>
          <Field label="버튼으로 시작" optional hint="화면이나 키패드 버튼의 이름이에요.">
            <WordsInput label="버튼으로 시작" value={h.buttons ?? []} onChange={(v) => { const n = { ...h }; if (v.length) n.buttons = v; else delete n.buttons; onHeader(n); }} />
          </Field>
        </>
      )}
      <Disclosure title="개발 정보" summary={flowId}>
        <p className="mb-2 text-xs text-muted">미리 채우는 값, 끼어드는 말, 넘겨받는 값 같은 설정은 아직 여기서 고칠 수 없어요. 저장해도 그대로 남아요.</p>
        <pre className="max-h-64 overflow-auto rounded-lg bg-sunken p-3 text-xs text-ink-2">{JSON.stringify(rest, null, 2) === "{}" ? "추가 설정 없음" : JSON.stringify(rest, null, 2)}</pre>
        <Button className="mt-3" variant="danger" icon={<Trash2 size={15} />} onClick={async () => {
          if (!window.confirm(`${flowId} 시나리오를 지울까요? 게시하기 전까지는 엔진에 남아 있어요.`)) return;
          await api.del(`/bots/${bot.slug}/flows/${flowId}`); onDeleted();
        }}>이 시나리오 지우기</Button>
      </Disclosure>
    </div>
  );
}

// --- the editor ---

const toDraft = (f: FlowDetail["flow"]): FlowDraft => ({ start: f.start ?? null, nodes: f.nodes, order: f.node_order, header: f.header });
const edgeColor = (h: string) => (h === "yes" || h === "ok" ? "var(--ok-fg)" : h === "no" || h === "error" ? "var(--err-fg)" : "var(--edge)");

function Editor({ bot, detail, tools, doc }: { bot: Bot; detail: FlowDetail; tools: Tool[]; doc: TypesDoc | null }) {
  const flowId = detail.flow.id;
  const rf = useReactFlow();
  const nav = useNavigate();
  const toast = useToast();
  const { refresh } = useShell();
  const actions = useBotActions();
  const [base, setBase] = useState(() => toDraft(detail.flow));
  const [revision, setRevision] = useState(detail.flow.revision);
  const [d, setD] = useState(base);
  const [sel, setSel] = useState<string | null>(null);
  const [selEdge, setSelEdge] = useState<string | null>(null);
  const [tab, setTab] = useState<"node" | "flow">("flow");
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [rfNodes, setRfNodes] = useState<Node[]>([]);
  const layoutTimer = useRef<number | undefined>(undefined);
  const placed = useRef<Record<string, { x: number; y: number }>>({});   // where new steps go, until React Flow has them
  const dirty = JSON.stringify(d) !== JSON.stringify(base);
  useUnsavedWarning(dirty);

  const { data: report } = useFetch<Report | null>(`/bots/${bot.slug}/validation`, [bot.validated, bot.draft_revision]);
  const engineItems: Item[] = bot.validated && !dirty ? (report?.items ?? []).filter((i) => i.flow_id === flowId) : [];
  const local = useMemo(() => localProblems(d), [d]);
  const toolMap = useMemo(() => new Map(tools.map((t) => [t.name, t])), [tools]);

  // positions: the saved top-to-bottom layout when complete, otherwise an automatic one
  const initialPositions = useMemo(() => {
    const saved = detail.layout.nodes;
    const g = { nodes: detail.graph.nodes, edges: detail.graph.edges };
    if (detail.layout.direction === "TB" && g.nodes.every((n) => saved[n.id])) {
      const s = detail.flow.start && saved[detail.flow.start];
      return { ...saved, [START_ID]: s ? { x: s.x, y: s.y - 190 } : { x: 0, y: -190 } } as Record<string, { x: number; y: number }>;
    }
    return Object.fromEntries(autoLayout(g.nodes, g.edges, detail.graph.start, "TB").map((p) => [p.id, { x: p.x, y: p.y }]));
  }, [detail]);

  const persistLayout = useCallback((nodes: Node[]) => {
    window.clearTimeout(layoutTimer.current);
    layoutTimer.current = window.setTimeout(() => {
      const pos: Record<string, { x: number; y: number }> = {};
      nodes.forEach((n) => { if (n.id !== START_ID) pos[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) }; });
      void api.put(`/bots/${bot.slug}/flows/${flowId}/layout`, { direction: "TB", viewport: rf.getViewport(), nodes: pos });
    }, 400);
  }, [bot.slug, flowId, rf]);

  // rebuild cards from the draft, keeping what React Flow measured and where the user dragged
  useEffect(() => {
    setRfNodes((prev) => {
      const old = new Map(prev.map((n) => [n.id, n]));
      const card = (id: string): Node => ({
        id, type: "step", position: old.get(id)?.position ?? placed.current[id] ?? initialPositions[id] ?? { x: 0, y: 0 },
        measured: old.get(id)?.measured,
        data: { nid: id, body: d.nodes[id], tools: toolMap, isStart: d.start === id, note: cardNote(d.nodes[id], d.header, doc, bot.lang, toolMap),
                engine: engineItems.filter((i) => i.node_id === id).length, local: local.filter((p) => p.node === id).length },
      });
      return [
        { id: START_ID, type: "trigger", position: old.get(START_ID)?.position ?? initialPositions[START_ID] ?? { x: 0, y: -190 },
          measured: old.get(START_ID)?.measured, data: { header: d.header, hasStart: !!d.start }, deletable: false },
        ...d.order.filter((id) => d.nodes[id]).map(card),
      ];
    });
  }, [d, initialPositions, toolMap, doc, JSON.stringify(engineItems), local]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (detail.layout.viewport && detail.layout.direction === "TB") rf.setViewport(detail.layout.viewport);
    else window.setTimeout(() => rf.fitView({ padding: 0.15, maxZoom: 1 }), 60);
  }, [flowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const flowEdges: Edge[] = useMemo(() => [
    ...(d.start ? [{ id: "__start__:next", source: START_ID, sourceHandle: "next", target: d.start, targetHandle: "in", type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, color: "var(--brand-500)" }, style: { stroke: "var(--brand-500)", strokeWidth: 1.8 } } as Edge] : []),
    ...draftEdges(d).filter((e) => d.nodes[e.to]).map((e) => ({
      id: e.id, source: e.from, sourceHandle: e.handle, target: e.to, targetHandle: "in", type: "smoothstep",
      label: e.handle === "next" ? undefined : e.label, selected: selEdge === e.id, reconnectable: "target" as const,
      markerEnd: { type: MarkerType.ArrowClosed, color: edgeColor(e.handle) },
      style: { stroke: edgeColor(e.handle), strokeWidth: 1.8 },
      labelStyle: { fill: edgeColor(e.handle), fontWeight: 700 }, labelBgStyle: { fill: "var(--surface)" }, labelBgPadding: [6, 3] as [number, number],
    })),
  ], [d, selEdge]);

  const onNodesChange = (changes: NodeChange[]) => {
    setRfNodes((ns) => applyNodeChanges(changes.filter((c) => c.type !== "remove" && c.type !== "select"), ns));
  };
  const select = (id: string | null) => { setSel(id); setSelEdge(null); setTab(id ? "node" : "flow"); };

  const link = (from: string, handle: string, to: string | null) => {
    if (from === START_ID) setD((x) => ({ ...x, start: to }));
    else setD((x) => connect(x, from, handle, to));
  };
  const onConnect = (c: Connection) => { if (c.source && c.target && c.target !== START_ID) link(c.source, c.sourceHandle ?? "next", c.target); };
  const onReconnect = (old: Edge, c: Connection) => { if (c.target && c.target !== START_ID) link(old.source, old.sourceHandle ?? "next", c.target); };

  const add = (kind: Kind, init: Record<string, any> = {}) => {
    setAdding(false);
    const after = sel && d.nodes[sel] ? sel : null;
    const made = addNode(d, kind, after);
    const id = made.id;
    const draft = { ...made.draft, nodes: { ...made.draft.nodes, [id]: { ...made.draft.nodes[id], ...init } } };
    const anchor = after ? rfNodes.find((n) => n.id === after)?.position : null;
    const position = anchor ? { x: anchor.x + 40, y: anchor.y + 200 } : rf.screenToFlowPosition({ x: window.innerWidth / 2 - 300, y: window.innerHeight / 2 });
    placed.current[id] = position;
    setD(draft);
    select(id);
  };
  const remove = (id: string) => { setD((x) => removeNode(x, id)); setRfNodes((ns) => ns.filter((n) => n.id !== id)); select(null); };
  const removeEdge = (edgeId: string) => {
    const [from, handle] = edgeId.split(":");
    link(from, handle, null); setSelEdge(null);
  };
  const tidy = () => {
    const g = { nodes: d.order.map((id) => ({ id, type: d.nodes[id].type, data: d.nodes[id] })), edges: draftEdges(d).filter((e) => d.nodes[e.to]) };
    const placed = new Map(autoLayout(g.nodes, g.edges, d.start, "TB").map((p) => [p.id, { x: p.x, y: p.y }]));
    setRfNodes((ns) => { const out = ns.map((n) => ({ ...n, position: placed.get(n.id) ?? n.position })); persistLayout(out); return out; });
    window.setTimeout(() => rf.fitView({ padding: 0.15, maxZoom: 1, duration: 250 }), 60);
  };

  const save = async () => {
    setSaving(true);
    try {
      const out = await api.put<FlowDetail>(`/bots/${bot.slug}/flows/${flowId}`, { header: d.header, start: d.start, nodes: d.nodes, node_order: d.order, revision });
      const next = toDraft(out.flow);
      setBase(next); setD(next); setRevision(out.flow.revision);
      persistLayout(rfNodes); refresh();
      toast("초안을 저장했어요. 검증하면 엔진이 읽을 수 있는지 알 수 있어요");
    } catch (e) {
      toast(e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 새로 고친 뒤 다시 해 주세요" : (e as Error).message, "err");
    } finally { setSaving(false); }
  };

  const onKey = (e: React.KeyboardEvent) => {
    const tag = (e.target as HTMLElement).tagName;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
    if ((e.key === "Delete" || e.key === "Backspace") && (sel || selEdge)) {
      e.preventDefault();
      if (selEdge) removeEdge(selEdge);
      else if (sel && window.confirm("이 단계를 지울까요? 이어진 선도 함께 지워져요.")) remove(sel);
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (dirty) void save(); }
    if (e.key === "Escape") setAdding(false);
  };

  const errCount = engineItems.length;
  const status = dirty ? <StatusChip tone="warn">저장하지 않은 변경</StatusChip>
    : !bot.validated ? <StatusChip tone="idle">검증 전</StatusChip>
    : errCount ? <StatusChip tone="err">엔진 검사 문제 {errCount}개</StatusChip>
    : bot.valid ? <StatusChip tone="ok">검증 통과</StatusChip> : <StatusChip tone="warn">다른 파일에 고칠 곳이 있어요</StatusChip>;
  const next = dirty ? <Button variant="primary" size="sm" icon={<Save size={14} />} loading={saving} onClick={save}>초안 저장</Button>
    : !bot.validated ? <Button variant="primary" size="sm" icon={<ShieldCheck size={14} />} loading={actions.validating} onClick={() => void actions.validate()}>검증하기</Button>
    : bot.valid && bot.has_unpublished_changes ? <Button variant="primary" size="sm" icon={<Rocket size={14} />} onClick={actions.openPublish}>게시하기</Button> : null;

  const panelProblems = sel ? [
    ...engineItems.filter((i) => i.node_id === sel).map((i) => ({ text: i.message, engine: true })),
    ...local.filter((p) => p.node === sel).map((p) => ({ text: p.text, engine: false })),
  ] : [];
  const flowLevel = [...engineItems.filter((i) => !i.node_id).map((i) => i.message), ...local.filter((p) => !p.node).map((p) => p.text)];

  return (
    <main className="flex h-[calc(100vh-3.5rem)]" onKeyDown={onKey}>
      <div className="relative min-w-0 flex-1">
        <div className="absolute left-4 right-4 top-4 z-10 flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-xl bg-surface/95 px-3 py-2 shadow-sm ring-1 ring-line">
            <Link to={paths.bot(bot.slug, "flows")} aria-label="시나리오 목록으로" className="rounded p-0.5 text-muted hover:text-ink"
              onClick={(e) => { if (dirty && !window.confirm("저장하지 않은 변경이 있어요. 버리고 나갈까요?")) e.preventDefault(); }}><ArrowLeft size={16} /></Link>
            <h1 className="text-sm font-semibold text-ink">{flowId}</h1>
            {status}
            <span className="num whitespace-nowrap text-xs text-muted">단계 {d.order.length}개</span>
            {next}
          </div>
          <span className="flex-1" />
          <div className="relative">
            <Button icon={<Plus size={15} />} aria-haspopup="menu" aria-expanded={adding} onClick={() => setAdding((a) => !a)} className="shadow-sm">단계 추가</Button>
            {adding && (
              <div role="menu" aria-label="추가할 단계" className="absolute right-0 top-11 z-20 w-72 rounded-xl bg-surface p-1.5 shadow-xl ring-1 ring-line">
                {sel && d.nodes[sel] && <div className="px-2.5 pb-1.5 pt-1 text-xs text-muted">선택한 단계 다음에 이어 붙여요</div>}
                {KINDS.map((k) => { const m = KIND[k]; const I = m.icon; return (
                  <button key={k} role="menuitem" type="button" onClick={() => add(k)} className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-sunken focus-visible:bg-sunken">
                    <span className={cn("grid h-7 w-7 place-items-center rounded-md", m.soft)}><I size={15} aria-hidden /></span>
                    <span><span className="block text-sm font-medium text-ink">{m.label}</span><span className="block text-xs text-muted">{m.hint}</span></span>
                  </button>); })}
              </div>
            )}
          </div>
          <Button icon={<LayoutGrid size={15} />} onClick={tidy} className="shadow-sm">자동 정렬</Button>
        </div>
        <ReactFlow
          nodes={rfNodes.map((n) => (n.selected === (n.id === sel) ? n : { ...n, selected: n.id === sel }))} edges={flowEdges} nodeTypes={nodeTypes}
          onNodesChange={onNodesChange} onConnect={onConnect} onReconnect={onReconnect} deleteKeyCode={null}
          onNodeClick={(_, n) => select(n.id === START_ID ? null : n.id)} onEdgeClick={(_, e) => { setSelEdge(e.id.startsWith(START_ID) ? null : e.id); setSel(null); }}
          onPaneClick={() => { select(null); setAdding(false); }} onNodeDragStop={() => persistLayout(rfNodes)}
          isValidConnection={(c) => c.target !== START_ID && c.source !== c.target}
          minZoom={0.2} maxZoom={1.5} proOptions={{ hideAttribution: false }} style={{ background: "var(--canvas)" }}>
          <Background gap={22} color="var(--canvas-dot)" />
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap pannable zoomable position="bottom-right" nodeColor="var(--line-strong)" maskColor="rgb(127 127 127 / 0.12)" />
        </ReactFlow>
        {selEdge && (
          <div className="absolute bottom-6 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-xl bg-surface px-4 py-2 text-sm shadow-lg ring-1 ring-line">
            선을 골랐어요. 끝을 끌어 다른 단계에 놓거나
            <Button size="sm" variant="danger" icon={<Trash2 size={14} />} onClick={() => removeEdge(selEdge)}>선 지우기</Button>
          </div>
        )}
      </div>

      <aside aria-label="편집 패널" className="flex w-[380px] shrink-0 flex-col border-l border-line bg-surface max-lg:w-[320px]">
        <div role="tablist" aria-label="편집 대상" className="flex border-b border-line text-sm font-medium">
          {([["node", "선택한 단계"], ["flow", "시나리오 설정"]] as const).map(([k, l]) => (
            <button key={k} role="tab" type="button" id={`tab-${k}`} aria-controls="flow-panel" aria-selected={tab === k} onClick={() => setTab(k)}
              className={cn("flex-1 border-b-2 px-4 py-3", tab === k ? "border-brand-500 text-brand-700" : "border-transparent text-muted hover:text-ink")}>{l}</button>
          ))}
        </div>
        <div id="flow-panel" className="min-h-0 flex-1 overflow-y-auto" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {flowLevel.length > 0 && <div className="px-5 pt-5"><Notice tone="warn" title="시나리오 전체">{flowLevel.join(" ")}</Notice></div>}
          {tab === "node" && sel && d.nodes[sel] ? (
            <NodeForm d={d} id={sel} tools={tools} doc={doc} lang={bot.lang} problems={panelProblems}
              onNode={(body) => setD((x) => ({ ...x, nodes: { ...x.nodes, [sel]: body } }))}
              onPatch={(patch, drop = []) => setD((x) => { const b = { ...x.nodes[sel], ...patch }; drop.forEach((k) => delete b[k]); return { ...x, nodes: { ...x.nodes, [sel]: b } }; })}
              onConnect={(h, to) => link(sel, h, to)} onRemove={() => remove(sel)} onMakeStart={() => setD((x) => ({ ...x, start: sel }))}
              onRename={(to) => { const p = rfNodes.find((n) => n.id === sel)?.position; if (p) placed.current[to] = p; setD((x) => renameNode(x, sel, to)); setSel(to); }} />
          ) : tab === "node" ? (
            <div className="space-y-3 p-5">
              <p className="text-sm text-muted">캔버스에서 단계를 누르거나 아래에서 골라 고쳐 보세요. 새 단계는 위의 <b className="text-ink-2">단계 추가</b>로 넣어요.</p>
              <ul className="space-y-1" aria-label="단계 목록">
                {d.order.map((id) => { const k = KIND[d.nodes[id].type as Kind] ?? KIND.goto; const I = k.icon; return (
                  <li key={id}><button type="button" onClick={() => select(id)} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] hover:bg-sunken">
                    <span className={cn("grid h-6 w-6 shrink-0 place-items-center rounded", k.soft)}><I size={13} aria-hidden /></span>
                    <span className="min-w-0 flex-1 truncate text-ink">{k.label}<span className="ml-1.5 text-muted">{String(d.nodes[id].text ?? d.nodes[id].prompt ?? d.nodes[id].tool ?? "")}</span></span>
                    {d.start === id && <span className="text-xs font-medium text-brand-700">첫 단계</span>}
                  </button></li>); })}
              </ul>
            </div>
          ) : (
            <FlowSettings bot={bot} flowId={flowId} d={d} doc={doc} onHeader={(h) => setD((x) => ({ ...x, header: h }))} setDraft={setD}
              onAddDefaultStep={(role) => add("confirm", { role_default: role })}
              onDeleted={() => { refresh(); toast("시나리오를 지웠어요"); nav(paths.bot(bot.slug, "flows")); }} />
          )}
        </div>
        <div className="flex items-center gap-2 border-t border-line px-5 py-3">
          <span className="flex-1 text-xs text-muted">{dirty ? "Ctrl+S로도 저장할 수 있어요" : "저장된 초안과 같아요"}</span>
          <Button disabled={!dirty} onClick={() => { if (window.confirm("저장하지 않은 변경을 모두 버릴까요?")) { setD(base); select(null); } }}>되돌리기</Button>
          <Button variant="primary" icon={<Save size={15} />} loading={saving} disabled={!dirty} onClick={save}>초안 저장</Button>
        </div>
      </aside>
    </main>
  );
}

export default function FlowEditor({ bot }: { bot: Bot }) {
  const { flowId } = useParams();
  const { data: detail, error, loading, reload } = useFetch<FlowDetail>(`/bots/${bot.slug}/flows/${flowId}`);
  const { data: tools } = useFetch<Tool[]>(`/domains/${bot.domain}/tools`);
  const { data: types, error: typesError } = useFetch<TypesResponse>(`/domains/${bot.domain}/types`, [bot.shared_revision]);
  if (error) return <main className="p-8"><ErrorState error={error} onRetry={reload} what="시나리오" />
    <p className="mt-4"><Link className="text-sm font-medium text-brand-700" to={paths.bot(bot.slug, "flows")}>시나리오 목록으로</Link></p></main>;
  if (loading || !detail || !tools || (!types && !typesError)) return <main className="p-8"><LoadingBlock rows={6} label="시나리오를 불러오는 중" /></main>;
  return <ReactFlowProvider><Editor key={`${bot.slug}/${flowId}`} bot={bot} detail={detail} tools={tools} doc={types?.body ?? null} /></ReactFlowProvider>;
}

