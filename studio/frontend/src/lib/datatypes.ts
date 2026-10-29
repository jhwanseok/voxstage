/** Types, roles and call bindings (ADR 0014): reading and writing the file shapes, and what the editor may offer.
 *  The engine loader has the last word; nothing here is a second copy of its data-flow check. */
import { edges, type FlowDraft } from "./flowEdit";

export type Labels = Record<string, string>;
export interface FieldSpec { type: string; length?: number; values?: string[]; label?: Labels; [k: string]: any }
export interface TypeDef { label?: Labels; fields?: Record<string, string | FieldSpec>; scalar?: string; [k: string]: any }
export interface RoleDef {
  type: string; scope?: "flow" | "session"; label?: Labels; filled_by?: string;
  default?: { from: string; ask?: string }; [k: string]: any;
}
export interface TypesDoc { types: Record<string, TypeDef>; roles: Record<string, RoleDef>; [k: string]: any }
export interface TypeUse { role: string; scope: "flow" | "session"; bot?: string; flow?: string }
export interface TypesResponse {
  domain: string; exists: boolean; revision: number; body: TypesDoc; usage: Record<string, TypeUse[]>;
  field_types: string[]; affects_bots: string[];
}

export const TYPE_NAME = /^[A-Z][A-Za-z0-9]*$/;
export const NAME = /^[a-z][a-z0-9_]*$/;

/** `name: text` and `name: {type: text}` are one field; the short form is written back when nothing else is set. */
export const fieldSpec = (v: string | FieldSpec | undefined): FieldSpec => (typeof v === "string" ? { type: v } : { type: "text", ...(v ?? {}) });
export function fieldOut(s: FieldSpec): string | FieldSpec {
  const o: FieldSpec = { ...s };
  Object.keys(o).forEach((k) => (o[k] === undefined || o[k] === "" || (k === "label" && !Object.keys(o.label ?? {}).length)) && delete o[k]);
  return Object.keys(o).length === 1 ? o.type : o;
}

export const labelOf = (o: { label?: Labels } | undefined, name: string, lang: string) => o?.label?.[lang] || name;

/** Set the label of one language; the other languages' labels stay as they are (Q54: labels live in the files). */
export function withLabel<T extends { label?: Labels }>(o: T, lang: string, text: string): T {
  const label = { ...(o.label ?? {}) };
  if (text.trim()) label[lang] = text.trim(); else delete label[lang];
  const out: T = { ...o, label };
  if (!Object.keys(label).length) delete (out as { label?: Labels }).label;
  return out;
}

export interface RoleRef { name: string; def: RoleDef; scope: "flow" | "session" }
export function rolesOf(header: Record<string, any>, doc: TypesDoc | null): RoleRef[] {
  const flow = Object.entries((header.roles ?? {}) as Record<string, RoleDef>).map(([name, def]) => ({ name, def, scope: "flow" as const }));
  const session = Object.entries(doc?.roles ?? {}).map(([name, def]) => ({ name, def, scope: "session" as const }));
  return [...flow, ...session];
}

export interface FieldOption { role: string; field: string; spec: FieldSpec; label: string; scope: "flow" | "session" }
/** Every role field a step can ask for or bind, labelled "예약자의 이름". */
export function fieldOptions(header: Record<string, any>, doc: TypesDoc | null, lang: string): FieldOption[] {
  const out: FieldOption[] = [];
  for (const r of rolesOf(header, doc)) {
    const t = doc?.types[r.def.type];
    for (const [field, v] of Object.entries(t?.fields ?? {})) {
      const spec = fieldSpec(v);
      out.push({ role: r.name, field, spec, scope: r.scope, label: `${labelOf(r.def, r.name, lang)}의 ${labelOf(spec, field, lang)}` });
    }
  }
  return out;
}

/** Tool params are a list of names today and a map of typed specs after A2; both read the same. */
export function paramNames(tool: Record<string, any> | undefined): string[] {
  const p = tool?.params;
  return Array.isArray(p) ? p : p && typeof p === "object" ? Object.keys(p) : [];
}
export function paramSpec(tool: Record<string, any> | undefined, name: string): FieldSpec | null {
  const p = tool?.params;
  return p && !Array.isArray(p) && typeof p === "object" && p[name] !== undefined ? fieldSpec(p[name]) : null;
}
export const returnNames = (tool: Record<string, any> | undefined): string[] => Object.keys(tool?.returns ?? {});

/** A field fits a parameter when the parameter has no type yet, or the types (and lengths, when both say) agree. */
export function fits(param: FieldSpec | null, field: FieldSpec | null): boolean {
  if (!param?.type || !field?.type) return true;
  if (param.type !== field.type) return false;
  return param.length == null || field.length == null || param.length === field.length;
}

export type Source = { role: string; field: string } | { call: string; field: string } | { const: string | number };
export type Binding =
  | { kind: "role"; role: string; field: string }
  | { kind: "call"; call: string; field: string }
  | { kind: "const"; value: string }
  | { kind: "legacy"; slot: string; text: string }     // args: {p: "{slot}"}, read as the flat slot
  | { kind: "template"; text: string }                  // args with more than one placeholder: shown, not edited
  | { kind: "none" };

const ONE_PLACEHOLDER = /^\{\s*([A-Za-z_]\w*)\s*\}$/;

export function bindingOf(node: Record<string, any>, p: string): Binding {
  const s = node.bind?.[p];
  if (s && typeof s === "object") {
    if ("role" in s) return { kind: "role", role: s.role, field: s.field };
    if ("call" in s) return { kind: "call", call: s.call, field: s.field };
    if ("const" in s) return { kind: "const", value: String(s.const) };
  }
  const a = node.args?.[p];
  if (a === undefined) return { kind: "none" };
  const m = typeof a === "string" ? ONE_PLACEHOLDER.exec(a) : null;
  return m ? { kind: "legacy", slot: m[1], text: a } : { kind: "template", text: String(a) };
}

/** Bind one parameter (or with `null` unbind it). A parameter is in `args` or in `bind`, never both. */
export function setBinding(node: Record<string, any>, p: string, src: Source | null): Record<string, any> {
  const b = { ...node };
  const args = { ...(b.args ?? {}) };
  delete args[p];
  if (Object.keys(args).length) b.args = args; else delete b.args;
  const bind = { ...(b.bind ?? {}) };
  if (src) bind[p] = src; else delete bind[p];
  if (Object.keys(bind).length) b.bind = bind; else delete b.bind;
  return b;
}

/** After a role is renamed, the steps that ask for it and the bindings that read it follow. */
export function renameRoleRefs(nodes: FlowDraft["nodes"], from: string, to: string): FlowDraft["nodes"] {
  const out: FlowDraft["nodes"] = {};
  for (const [id, n] of Object.entries(nodes)) {
    let b = n.role === from ? { ...n, role: to } : n;
    if (b.role_default === from) b = { ...b, role_default: to };
    if (b.bind) b = { ...b, bind: Object.fromEntries(Object.entries(b.bind as Record<string, any>).map(([p, s]) => [p, s?.role === from ? { ...s, role: to } : s])) };
    out[id] = b;
  }
  return out;
}

/** Calls whose result a step can read: `always` succeeded on every path from the start, `sometimes` on some only.
 *  A call's result exists after its "성공" exit, not after "실패". */
export function callsBefore(d: FlowDraft, target: string): { always: string[]; sometimes: string[] } {
  const calls = d.order.filter((id) => d.nodes[id]?.type === "call");
  const es = edges(d).filter((e) => d.nodes[e.to]);
  const all = new Set(calls);
  const must = new Map<string, Set<string>>();
  const may = new Map<string, Set<string>>();
  for (const id of d.order) { must.set(id, new Set(all)); may.set(id, new Set()); }
  if (!d.start || !d.nodes[d.start]) return { always: [], sometimes: [] };
  const reached = new Set<string>([d.start]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const id of d.order) {
      const preds = es.filter((e) => e.to === id && reached.has(e.from));
      if (preds.length) reached.add(id);
      const out = (e: typeof es[number], m: Map<string, Set<string>>) => {
        const s = new Set(m.get(e.from));
        if (d.nodes[e.from].type === "call" && e.handle === "ok") s.add(e.from);
        return s;
      };
      const ins = preds.map((e) => out(e, must));
      const mu = id === d.start ? new Set<string>() : ins.length ? ins.reduce((a, b) => new Set([...a].filter((x) => b.has(x)))) : new Set(all);
      const ma = new Set(preds.flatMap((e) => [...out(e, may)]));
      if (mu.size !== must.get(id)!.size || ma.size !== may.get(id)!.size) changed = true;
      must.set(id, mu); may.set(id, ma);
    }
  }
  if (!reached.has(target)) return { always: [], sometimes: [] };
  const always = calls.filter((c) => must.get(target)!.has(c));
  return { always, sometimes: calls.filter((c) => may.get(target)!.has(c) && !always.includes(c)) };
}

/** Steps that confirm a role's default (P3: an explicit `confirm` with `role_default`). */
export const defaultSteps = (d: FlowDraft, role: string) => d.order.filter((id) => d.nodes[id]?.role_default === role);
