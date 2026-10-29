import dagre from "@dagrejs/dagre";
import type { GraphEdge, GraphNode } from "../api";

export const NODE_W = 280;
export const START_ID = "__start__";

/** Rough card height of the editor (kind line, up to three lines of text, the exits row), so dagre leaves room. */
export function nodeHeight(n: GraphNode): number {
  return n.type === "end" ? 96 : 136;
}

export interface Placed { id: string; x: number; y: number }

/** Automatic layout (docs/studio/screens.md): dagre, ranked from Start; cycles are broken by dagre. */
export function autoLayout(nodes: GraphNode[], edges: GraphEdge[], start: string | null, dir: "LR" | "TB" = "LR"): Placed[] {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: dir, nodesep: 40, ranksep: dir === "TB" ? 64 : 90, acyclicer: "greedy" });
  g.setDefaultEdgeLabel(() => ({}));
  g.setNode(START_ID, dir === "TB" ? { width: NODE_W, height: 120 } : { width: 70, height: 36 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: nodeHeight(n) }));
  if (start && nodes.some((n) => n.id === start)) g.setEdge(START_ID, start);
  const back = backEdges(nodes, edges, start);
  edges.forEach((e) => {
    if (g.hasNode(e.from) && g.hasNode(e.to) && e.from !== e.to && !back.has(e.id)) g.setEdge(e.from, e.to);
  });
  dagre.layout(g);
  return [START_ID, ...nodes.map((n) => n.id)].map((id) => {
    const p = g.node(id);
    return { id, x: Math.round(p.x - p.width / 2), y: Math.round(p.y - p.height / 2) };
  });
}

/** Edges that close a cycle in a depth-first walk from Start (a retry loop to an earlier question). They are
 *  left out of the ranking so the forward flow reads left to right. */
export function backEdges(nodes: GraphNode[], edges: GraphEdge[], start: string | null): Set<string> {
  const out = new Map<string, GraphEdge[]>();
  edges.forEach((e) => out.set(e.from, [...(out.get(e.from) ?? []), e]));
  const state = new Map<string, 1 | 2>();   // 1: on the stack, 2: done
  const back = new Set<string>();
  const visit = (id: string) => {
    state.set(id, 1);
    for (const e of out.get(id) ?? []) {
      if (state.get(e.to) === 1) back.add(e.id);
      else if (!state.has(e.to)) visit(e.to);
    }
    state.set(id, 2);
  };
  if (start) visit(start);
  nodes.forEach((n) => { if (!state.has(n.id)) visit(n.id); });
  return back;
}

/** Exits of a node as drawn: handle id and label, in order (the same table as the engine NodeType.edges). */
export function exits(n: GraphNode): { handle: string; label: string }[] {
  const d = n.data;
  switch (n.type) {
    case "confirm": return [{ handle: "yes", label: "yes" }, { handle: "no", label: "no" }];
    case "call": return [{ handle: "ok", label: "ok" }, { handle: "error", label: "error" }];
    case "branch":
      return [...(d.cases ?? []).map((c: any, i: number) => ({ handle: `case-${i}`, label: String(c.when) })),
              { handle: "else", label: "else" }];
    case "end": return [];
    default: return [{ handle: "next", label: "" }];
  }
}
