/** The scenario editor's parts for ADR 0014: the flow's roles, asking for a role's field, the role-default step and
 *  the call binding form. Shapes come from `lib/datatypes.ts`; the engine checks the data flow at validation. */
import { Plus, Trash2, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import type { Bot, Tool } from "../api";
import { EXTRACTORS } from "../copy";
import {
  bindingOf, callsBefore, defaultSteps, fieldOptions, fits, labelOf, NAME, paramNames, paramSpec, renameRoleRefs, RESERVED,
  returnNames, rolesOf, setBinding, withLabel, type FieldSpec, type RoleDef, type Source, type TypesDoc,
} from "../lib/datatypes";
import type { FlowDraft } from "../lib/flowEdit";
import { paths } from "../paths";
import { Button, eul, Field, IconButton, Input, josa, Notice, Select, Tag } from "../ui";

/** The values a choice stores: the words of a list, or the values of a word -> value map. */
const choiceValues = (s: FieldSpec) => (Array.isArray(s.choices) ? s.choices : Object.values(s.choices ?? {})).map(String);
const specText = (s: FieldSpec | null) => (s ? `${EXTRACTORS[s.type] ?? s.type}${s.length ? ` ${s.length}자리` : ""}` : "");

/** "예약자의 이름" for a role path, the raw path when the role or field is gone. */
export function fieldLabel(header: Record<string, any>, doc: TypesDoc | null, lang: string, role: string, field: string): string {
  return fieldOptions(header, doc, lang).find((o) => o.role === role && o.field === field)?.label ?? `${role}.${field}`;
}

// --- 이 시나리오의 사람과 값 ---

export function RolesSection({ bot, d, doc, setDraft, onAddDefaultStep }: {
  bot: Bot; d: FlowDraft; doc: TypesDoc | null; setDraft: (f: (x: FlowDraft) => FlowDraft) => void; onAddDefaultStep: (role: string) => void;
}) {
  const roles: Record<string, RoleDef> = d.header.roles ?? {};
  const records = Object.entries(doc?.types ?? {});
  const session = Object.entries(doc?.session_roles ?? {});
  const setRoles = (next: Record<string, RoleDef>) => setDraft((x) => {
    const header = { ...x.header };
    if (Object.keys(next).length) header.roles = next; else delete header.roles;
    return { ...x, header };
  });
  const patch = (name: string, r: RoleDef) => setRoles(Object.fromEntries(Object.entries(roles).map(([n, v]) => [n, n === name ? r : v])));
  const rename = (from: string, to: string) => setDraft((x) => ({
    ...x, nodes: renameRoleRefs(x.nodes, from, to),
    header: { ...x.header, roles: Object.fromEntries(Object.entries(roles).map(([n, v]) => [n === from ? to : n,
      v.default?.from === from ? { ...v, default: { ...v.default, from: to } } : v])) },
  }));
  const add = () => {
    let n = Object.keys(roles).length + 1;
    while (roles[`role_${n}`]) n += 1;
    setRoles({ ...roles, [`role_${n}`]: { type: records[0][0] } });
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-semibold text-ink">이 시나리오의 속성</div>
        <p className="mt-0.5 text-xs text-muted">이 시나리오 안에서만 써요. 예약자와 방문자처럼 같은 종류를 다른 이름으로 두 번 쓸 수 있어요.</p>
      </div>
      {!records.length && (
        <Notice tone="idle" title="속성 종류가 아직 없어요">
          <Link className="font-medium text-brand-700 underline" to={paths.bot(bot.slug, "data")}>데이터</Link>에서 사람 같은 종류를 먼저 만들어 주세요.
        </Notice>
      )}
      {Object.entries(roles).map(([name, r]) => {
        const sameType = Object.entries(roles).filter(([n, v]) => n !== name && v.type === r.type);
        const idTaken = (to: string) => to !== name && (!!roles[to] || RESERVED.has(to) || !!d.nodes[to]);
        const steps = defaultSteps(d, name);
        return (
          <div key={name} className="space-y-3 rounded-lg border border-line p-3">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700"><UserRound size={14} aria-hidden /></span>
              <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink">{labelOf(r, name, bot.lang)}</span>
              <IconButton label={`${labelOf(r, name, bot.lang)} 지우기`} onClick={() => { const { [name]: _g, ...rest } = roles; setRoles(rest); }}><Trash2 size={14} /></IconButton>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="표시 이름"><Input value={r.label?.[bot.lang] ?? ""} placeholder="예: 방문자" onChange={(e) => patch(name, withLabel(r, bot.lang, e.target.value))} /></Field>
              <Field label="속성 종류">
                <Select value={r.type} onChange={(e) => { const { default: _d, ...rest } = r; patch(name, { ...rest, type: e.target.value }); }}>
                  {!records.some(([t]) => t === r.type) && <option value={r.type}>{r.type} (없음)</option>}
                  {records.map(([tid, t]) => <option key={tid} value={tid}>{labelOf(t, tid, bot.lang)}</option>)}
                </Select>
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="h-4 w-4 accent-[var(--brand-500)]" checked={!!r.default} disabled={!sameType.length && !r.default}
                onChange={(e) => { const { default: _d, ...rest } = r; patch(name, e.target.checked ? { ...rest, default: { from: sameType[0][0] } } : rest); }} />
              다른 사람과 같을 수 있어요
              {!sameType.length && !r.default && <span className="text-xs text-muted">(같은 종류가 하나 더 있어야 해요)</span>}
            </label>
            {r.default && (
              <div className="space-y-2 rounded-lg bg-sunken p-3">
                <Field label="누구와 같은지">
                  <Select value={r.default.from} onChange={(e) => patch(name, { ...r, default: { from: e.target.value } })}>
                    {!sameType.some(([n]) => n === r.default!.from) && <option value={r.default.from}>{r.default.from} (없음)</option>}
                    {sameType.map(([n, v]) => <option key={n} value={n}>{labelOf(v, n, bot.lang)}</option>)}
                  </Select>
                </Field>
                <p className="text-xs text-ink-2">예/아니오 확인 단계에서 같은 분인지 물어요. 예면 그 사람의 속성을 그대로 쓰고, 아니오면 이어지는 단계에서 이 사람의 속성을 물어요.</p>
                {steps.length ? <p className="text-xs text-ok-fg">확인 단계가 있어요 ({steps.join(", ")})</p> : (
                  <Notice tone="warn" title="확인 단계가 없어요" action={<Button size="sm" onClick={() => onAddDefaultStep(name)}>확인 단계 추가</Button>}>
                    같은지 묻는 예/아니오 확인 단계가 있어야 게시할 수 있어요.
                  </Notice>
                )}
              </div>
            )}
            <Field label="이름" hint="파일과 엔진 메시지에서 가리켜요. 바꾸면 묻는 단계와 넘길 속성도 함께 바뀌어요."
              error={null}>
              <RenameInput value={name} valid={(to) => NAME.test(to) && !idTaken(to)} onRename={(to) => rename(name, to)} />
            </Field>
          </div>
        );
      })}
      <Button size="sm" variant="ghost" icon={<Plus size={14} />} disabled={!records.length} onClick={add}>속성 추가</Button>
      {session.length > 0 && (
        <p className="text-xs text-muted">
          통화 전체에서 쓰는 속성: {session.map(([n, v]) => labelOf(v, n, bot.lang)).join(", ")}. 고치려면 <Link className="font-medium text-brand-700 underline" to={paths.bot(bot.slug, "data")}>데이터</Link>로 가세요.
        </p>
      )}
    </div>
  );
}

function RenameInput({ value, valid, onRename }: { value: string; valid: (to: string) => boolean; onRename: (to: string) => void }) {
  return (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const to = String(new FormData(e.currentTarget).get("to") ?? ""); if (to !== value && valid(to)) onRename(to); }}>
      <Input key={value} name="to" aria-label="새 이름" className="font-mono text-[13px]" defaultValue={value} />
      <Button type="submit">바꾸기</Button>
    </form>
  );
}

// --- 묻기: 누구의 어떤 값 ---

export function AskTarget({ d, doc, lang, b, onPatch }: {
  d: FlowDraft; doc: TypesDoc | null; lang: string; b: Record<string, any>; onPatch: (patch: Record<string, any>, drop?: string[]) => void;
}) {
  const opts = fieldOptions(d.header, doc, lang).filter((o) => o.scope === "flow");
  if (!opts.length && !b.role) return null;
  const value = b.role ? `${b.role}.${b.field ?? ""}` : "";
  const known = opts.find((o) => `${o.role}.${o.field}` === value);
  return (
    <Field label="받을 속성" hint={known ? `형식은 속성 종류에서 정해요: ${specText(known.spec)}` : "이 시나리오의 속성 중에서 고르거나, 이름만 붙여 받아요."}
      error={b.role && !known ? `${josa(value, "이", "가")} 이 시나리오에 없어요` : null}>
      <Select value={value} onChange={(e) => {
        const o = opts.find((x) => `${x.role}.${x.field}` === e.target.value);
        if (!o) { onPatch({ slot: b.slot ?? b.field ?? "" }, ["role", "field"]); return; }
        onPatch({ role: o.role, field: o.field }, ["slot", "extractor", "length", "choices"]);
      }}>
        <option value="">이름만 붙여 받기</option>
        {b.role && !known && <option value={value}>{value} (없음)</option>}
        {opts.map((o) => <option key={`${o.role}.${o.field}`} value={`${o.role}.${o.field}`}>{o.label}</option>)}
      </Select>
    </Field>
  );
}

// --- 예/아니오 확인: 같은 사람인지 ---

export function RoleDefaultField({ d, lang, doc, b, onPatch }: {
  d: FlowDraft; lang: string; doc: TypesDoc | null; b: Record<string, any>; onPatch: (patch: Record<string, any>, drop?: string[]) => void;
}) {
  const roles = Object.entries((d.header.roles ?? {}) as Record<string, RoleDef>).filter(([, r]) => r.default);
  if (!roles.length && !b.role_default) return null;
  const r = b.role_default ? (d.header.roles ?? {})[b.role_default] as RoleDef | undefined : undefined;
  const from = r?.default?.from;
  const fromDef = from ? d.header.roles?.[from] : undefined;
  return (
    <Field label="같은 사람인지 확인" optional
      hint={r && from ? `예면 ${labelOf(fromDef, from, lang)}의 속성을 ${labelOf(r, b.role_default, lang)}에 그대로 써요. 아니오면 이어지는 단계에서 물어요.` : "기본값이 있는 사람을 고르면 이 단계가 그 확인이 돼요."}
      error={b.role_default && !r?.default ? `${b.role_default}에 기본값이 없어요` : null}>
      <Select value={b.role_default ?? ""} onChange={(e) => (e.target.value ? onPatch({ role_default: e.target.value }) : onPatch({}, ["role_default"]))}>
        <option value="">확인하지 않음</option>
        {b.role_default && !r?.default && <option value={b.role_default}>{b.role_default} (없음)</option>}
        {roles.map(([n, v]) => <option key={n} value={n}>{labelOf(v, n, lang)}</option>)}
      </Select>
    </Field>
  );
}

// --- API 호출: 넘길 값 ---

type Choice = "" | "slot" | "const" | `role:${string}` | `call:${string}`;

function choiceOf(binding: ReturnType<typeof bindingOf>): Choice {
  switch (binding.kind) {
    case "role": return `role:${binding.role}.${binding.field}`;
    case "call": return `call:${binding.call}`;
    case "const": return "const";
    case "legacy": return "slot";
    default: return "";
  }
}

export function BindingForm({ d, id, tool, tools, doc, lang, onNode }: {
  d: FlowDraft; id: string; tool: Tool; tools: Tool[]; doc: TypesDoc | null; lang: string; onNode: (b: Record<string, any>) => void;
}) {
  const b = d.nodes[id];
  const params = paramNames(tool.body);
  const opts = fieldOptions(d.header, doc, lang);
  const before = callsBefore(d, id);
  const toolOf = (step: string) => tools.find((t) => t.name === d.nodes[step]?.tool);
  if (!params.length) return <p className="text-[13px] text-muted">이 API는 받는 속성이 없어요.</p>;
  const unbound = params.filter((p) => bindingOf(b, p).kind === "none").length;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-medium text-ink">넘길 속성</div>
        {unbound > 0 && <span className="text-xs font-medium text-warn-fg">연결 안 된 속성 {unbound}개</span>}
      </div>
      {params.map((p) => {
        const spec = paramSpec(tool.body, p);
        const cur = bindingOf(b, p);
        const choice = choiceOf(cur);
        const roleOpts = opts.filter((o) => fits(spec, o.spec));
        let error: string | null = null;
        if (cur.kind === "role") {
          const o = opts.find((x) => x.role === cur.role && x.field === cur.field);
          error = !o ? `${josa(`${cur.role}.${cur.field}`, "이", "가")} 지금은 없어요` : !fits(spec, o.spec) ? `형식이 맞지 않아요 (받는 쪽 ${specText(spec)}, 고른 속성 ${specText(o.spec)})` : null;
        } else if (cur.kind === "call") {
          error = d.nodes[cur.call]?.type !== "call" ? `${cur.call} API 호출 단계가 지금은 없어요`
            : !before.always.includes(cur.call) ? (before.sometimes.includes(cur.call) ? "일부 경로에서만 이 결과가 있어요" : "이 단계보다 앞에서 부르지 않아요") : null;
        }
        const set = (src: Source | null) => onNode(setBinding(b, p, src));
        const onChoice = (c: string) => {
          if (c === "") set(null);
          else if (c === "const") set({ const: "" });
          else if (c === "slot") onNode({ ...setBinding(b, p, null), args: { ...(setBinding(b, p, null).args ?? {}), [p]: `{${p}}` } });
          else if (c.startsWith("role:")) { const [role, field] = c.slice(5).split("."); set({ role, field }); }
          else if (c.startsWith("call:")) { const call = c.slice(5); set({ call, field: returnNames(toolOf(call)?.body)[0] ?? "" }); }
        };
        return (
          <div key={p} className="space-y-2 rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <code className="text-[13px] font-semibold text-ink">{p}</code>
              {spec && <span className="text-xs text-muted">{specText(spec)}</span>}
              {cur.kind === "legacy" && <Tag tone="idle">예전 방식</Tag>}
              {cur.kind === "template" && <Tag tone="idle">직접 쓴 식</Tag>}
              {cur.kind === "none" && <Tag tone="warn">연결 안 됨</Tag>}
            </div>
            {cur.kind === "template" && <code className="block rounded bg-sunken px-2 py-1 text-xs text-ink-2">{cur.text}</code>}
            <Field label="가져올 속성" error={error}>
              <Select value={cur.kind === "template" ? "__template" : choice} onChange={(e) => onChoice(e.target.value)}>
                {cur.kind === "template" && <option value="__template">지금 식 그대로 두기</option>}
                <option value="">연결하지 않음</option>
                {(roleOpts.length > 0 || cur.kind === "role") && (
                  <optgroup label="시나리오에서 수집한 속성">
                    {cur.kind === "role" && !roleOpts.some((o) => choice === `role:${o.role}.${o.field}`) && <option value={choice}>{cur.role}.{cur.field} (맞지 않음)</option>}
                    {roleOpts.map((o) => <option key={`${o.role}.${o.field}`} value={`role:${o.role}.${o.field}`}>{o.label}</option>)}
                  </optgroup>
                )}
                {(before.always.length + before.sometimes.length > 0 || cur.kind === "call") && (
                  <optgroup label="API로 얻은 속성">
                    {cur.kind === "call" && !before.always.includes(cur.call) && !before.sometimes.includes(cur.call) && <option value={choice}>{cur.call} (없음)</option>}
                    {before.always.map((c) => <option key={c} value={`call:${c}`}>{d.nodes[c].tool || c} 결과 ({c})</option>)}
                    {before.sometimes.map((c) => <option key={c} value={`call:${c}`} disabled={choice !== `call:${c}`}>{d.nodes[c].tool || c} 결과 ({c}): 일부 경로에서만 불러요</option>)}
                  </optgroup>
                )}
                <option value="const">고정값</option>
                <option value="slot">이름으로 받은 속성 (예전 방식)</option>
              </Select>
            </Field>
            {cur.kind === "call" && (() => {
              const rets = returnNames(toolOf(cur.call)?.body);
              return rets.length ? (
                <Field label="결과 중 어떤 항목">
                  <Select value={cur.field} onChange={(e) => set({ call: cur.call, field: e.target.value })}>
                    {!rets.includes(cur.field) && <option value={cur.field}>{cur.field || "고르기"}</option>}
                    {rets.map((r) => <option key={r} value={r}>{r}</option>)}
                  </Select>
                </Field>
              ) : (
                <Field label="결과 중 어떤 항목" hint="API 응답에 있는 이름이에요." error={cur.field ? null : "이름을 넣어 주세요"}>
                  <Input className="font-mono text-[13px]" value={cur.field} onChange={(e) => set({ call: cur.call, field: e.target.value })} />
                </Field>
              );
            })()}
            {cur.kind === "const" && (
              <Field label="넣을 값" error={cur.value === "" ? "값을 넣어 주세요" : null}>
                {spec?.type === "choice" && choiceValues(spec).length
                  ? <Select value={cur.value} onChange={(e) => set({ const: e.target.value })}><option value="">고르기</option>{choiceValues(spec).map((v) => <option key={v} value={v}>{v}</option>)}</Select>
                  : <Input inputMode={spec && ["digits", "number"].includes(spec.type) ? "numeric" : undefined} maxLength={spec?.type === "digits" ? spec.length : undefined}
                      value={cur.value} onChange={(e) => set({ const: spec?.type === "number" && e.target.value !== "" && !isNaN(Number(e.target.value)) ? Number(e.target.value) : e.target.value })} />}
              </Field>
            )}
            {cur.kind === "legacy" && (
              <Field label="받은 속성의 이름" hint="앞 단계에서 이 이름으로 받은 속성을 넘겨요. 시나리오의 속성을 쓰면 엔진이 게시 전에 형식과 경로를 검사해요.">
                <Input className="font-mono text-[13px]" value={cur.slot} onChange={(e) => onNode({ ...b, args: { ...(b.args ?? {}), [p]: `{${e.target.value}}` } })} />
              </Field>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** One line under a card: what an `ask` fills, which role a confirm settles, how many params a call leaves open. */
export function cardNote(body: Record<string, any>, header: Record<string, any>, doc: TypesDoc | null, lang: string, tools: Map<string, Tool>): string | null {
  if (body.type === "ask" && body.role) return `${eul(fieldLabel(header, doc, lang, body.role, body.field ?? ""))} 받아요`;
  if (body.type === "confirm" && body.role_default) {
    const r = (header.roles ?? {})[body.role_default] as RoleDef | undefined;
    const from = r?.default?.from;
    if (!r || !from) return null;
    return `${josa(labelOf(r, body.role_default, lang), "이", "가")} ${josa(labelOf(header.roles?.[from], from, lang), "과", "와")} 같은지 물어요`;
  }
  if (body.type === "call" && body.tool) {
    const open = paramNames(tools.get(body.tool)?.body).filter((p) => bindingOf(body, p).kind === "none").length;
    return open ? `연결 안 된 속성 ${open}개` : null;
  }
  return null;
}

