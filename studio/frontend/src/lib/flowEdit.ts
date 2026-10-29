/** Editing a flow draft: the same exits as the engine's `NodeType.edges` (studio_backend/service.py `_edges`).
 *  Every operation returns a new draft; nothing here talks to the server. */
import type { GraphEdge } from "../api";

export type Kind = "say" | "ask" | "form" | "confirm" | "call" | "branch" | "notices" | "goto" | "end";
export const KINDS: Kind[] = ["say", "ask", "confirm", "call", "branch", "notices", "form", "goto", "end"];

export interface FlowDraft {
  start: string | null;
  nodes: Record<string, Record<string, any>>;
  order: string[];
  header: Record<string, any>;
}

export interface Exit { handle: string; label: string; target: string | null }

/** A new step of each kind, filled so the form shows every field. */
export function blank(kind: Kind): Record<string, any> {
  switch (kind) {
    case "say": return { type: "say", text: "" };
    case "ask": return { type: "ask", slot: "", prompt: "", extractor: "text" };
    case "form": return { type: "form", slots: [] };
    case "confirm": return { type: "confirm", prompt: "" };
    case "call": return { type: "call", tool: "", args: {} };
    case "branch": return { type: "branch", cases: [{ when: "", next: null }] };
    case "notices": return { type: "notices" };
    case "goto": return { type: "goto" };
    case "end": return { type: "end" };
  }
}

export function exits(body: Record<string, any>): Exit[] {
  const t = body.type as Kind;
  const one = (handle: string, label: string, key: string): Exit => ({ handle, label, target: body[key] ?? null });
  switch (t) {
    case "confirm": return [one("yes", "예", "on_yes"), one("no", "아니오", "on_no")];
    case "call": return [one("ok", "성공", "on_ok"), one("error", "실패", "on_error")];
    case "branch":
      return [...(body.cases ?? []).map((c: any, i: number) => ({ handle: `case-${i}`, label: `조건 ${i + 1}`, target: c?.next ?? null })),
              one("else", "그 밖", "else")];
    case "end": return [];
    default: return [one("next", "다음", "next")];
  }
}

/** Set (or with `null` clear) where one exit of a node leads. */
export function setTarget(body: Record<string, any>, handle: string, target: string | null): Record<string, any> {
  const b = { ...body };
  const put = (key: string) => { if (target === null) delete b[key]; else b[key] = target; };
  if (handle === "next") put("next");
  else if (handle === "yes") put("on_yes");
  else if (handle === "no") put("on_no");
  else if (handle === "ok") put("on_ok");
  else if (handle === "error") put("on_error");
  else if (handle === "else") put("else");
  else if (handle.startsWith("case-")) {
    const i = Number(handle.slice(5));
    b.cases = (b.cases ?? []).map((c: any, j: number) => (j === i ? { ...c, next: target } : c));
  }
  return b;
}

export function edges(d: FlowDraft): GraphEdge[] {
  const out: GraphEdge[] = [];
  for (const id of d.order) {
    const body = d.nodes[id];
    if (!body) continue;
    for (const e of exits(body)) {
      if (e.target) out.push({ id: `${id}:${e.handle}`, from: id, to: e.target, label: e.label, handle: e.handle });
    }
  }
  return out;
}

export function newId(kind: Kind, nodes: Record<string, unknown>): string {
  let n = 1;
  while (nodes[`${kind}_${n}`]) n += 1;
  return `${kind}_${n}`;
}

/** Add a step; with `after`, the first empty exit of that step leads to it. The first step of an empty flow starts it. */
export function addNode(d: FlowDraft, kind: Kind, after?: string | null): { draft: FlowDraft; id: string } {
  const id = newId(kind, d.nodes);
  let nodes = { ...d.nodes, [id]: blank(kind) };
  if (after && nodes[after]) {
    const free = exits(nodes[after]).find((e) => !e.target);
    if (free) nodes = { ...nodes, [after]: setTarget(nodes[after], free.handle, id) };
  }
  return { draft: { ...d, nodes, order: [...d.order, id], start: d.start ?? id }, id };
}

/** Remove a step and every link to it; if it was the start, the flow has no start until one is chosen. */
export function removeNode(d: FlowDraft, id: string): FlowDraft {
  const nodes: FlowDraft["nodes"] = {};
  for (const [nid, body] of Object.entries(d.nodes)) {
    if (nid === id) continue;
    let b = body;
    for (const e of exits(body)) if (e.target === id) b = setTarget(b, e.handle, null);
    nodes[nid] = b;
  }
  return { ...d, nodes, order: d.order.filter((x) => x !== id), start: d.start === id ? null : d.start };
}

export function connect(d: FlowDraft, from: string, handle: string, to: string | null): FlowDraft {
  if (!d.nodes[from]) return d;
  return { ...d, nodes: { ...d.nodes, [from]: setTarget(d.nodes[from], handle, to) } };
}

export const VALID_ID = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Rename a step, every link to it and every binding that reads its result (ids appear in YAML and in the engine's messages). */
export function renameNode(d: FlowDraft, from: string, to: string): FlowDraft {
  if (from === to || !d.nodes[from] || d.nodes[to] || !VALID_ID.test(to)) return d;
  const nodes: FlowDraft["nodes"] = {};
  for (const nid of Object.keys(d.nodes)) {
    let b = d.nodes[nid];
    for (const e of exits(b)) if (e.target === from) b = setTarget(b, e.handle, to);
    if (b.bind) b = { ...b, bind: Object.fromEntries(Object.entries(b.bind as Record<string, any>).map(([p, s]) => [p, s?.call === from ? { ...s, call: to } : s])) };
    nodes[nid === from ? to : nid] = b;
  }
  return { ...d, nodes, order: d.order.map((x) => (x === from ? to : x)), start: d.start === from ? to : d.start };
}

/** Problems a draft has before the engine sees it: missing start, links to nowhere, steps nothing leads to. */
export function localProblems(d: FlowDraft): { node: string | null; text: string }[] {
  const out: { node: string | null; text: string }[] = [];
  if (!d.start) out.push({ node: null, text: "시작 단계가 없어요" });
  const reached = new Set<string>();
  const walk = (id: string | null) => {
    if (!id || reached.has(id) || !d.nodes[id]) return;
    reached.add(id);
    exits(d.nodes[id]).forEach((e) => walk(e.target));
  };
  walk(d.start);
  for (const id of d.order) {
    const body = d.nodes[id];
    for (const e of exits(body)) {
      if (e.target && !d.nodes[e.target]) out.push({ node: id, text: `"${e.label}" 다음 단계가 없어요` });
    }
    if (body.type !== "end" && body.type !== "branch" && exits(body).some((e) => !e.target) && body.type !== "call")
      out.push({ node: id, text: "다음 단계가 이어지지 않았어요" });
    if (body.type === "call" && !body.on_ok) out.push({ node: id, text: "성공했을 때 갈 곳이 없어요" });
    if (d.start && !reached.has(id)) out.push({ node: id, text: "시작에서 닿지 않는 단계예요" });
  }
  if (!Object.values(d.nodes).some((b) => b.type === "end")) out.push({ node: null, text: "끝내기 단계가 하나는 있어야 해요" });
  return out;
}
