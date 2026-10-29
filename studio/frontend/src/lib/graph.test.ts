import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode } from "../api";
import { START_ID, autoLayout, exits } from "./graph";

const n = (id: string, type: string, data: any = {}): GraphNode => ({ id, type, data });

describe("graph", () => {
  const nodes = [n("a", "ask"), n("b", "call"), n("c", "say"), n("d", "end")];
  const edges: GraphEdge[] = [
    { id: "a:next", from: "a", to: "b", label: "", handle: "next" },
    { id: "b:ok", from: "b", to: "c", label: "ok", handle: "ok" },
    { id: "b:error", from: "b", to: "d", label: "error", handle: "error" },
    { id: "c:next", from: "c", to: "d", label: "", handle: "next" },
    { id: "d:back", from: "d", to: "a", label: "", handle: "next" }, // a back-edge must not break the layout
  ];
  it("places start first and ranks left to right", () => {
    const p = Object.fromEntries(autoLayout(nodes, edges, "a").map((x) => [x.id, x]));
    expect(p[START_ID].x).toBeLessThan(p.a.x);
    expect(p.a.x).toBeLessThan(p.b.x);
    expect(p.b.x).toBeLessThan(p.c.x);
  });
  it("draws the exits the engine has for each kind", () => {
    expect(exits(n("x", "confirm")).map((e) => e.handle)).toEqual(["yes", "no"]);
    expect(exits(n("x", "call")).map((e) => e.handle)).toEqual(["ok", "error"]);
    expect(exits(n("x", "end"))).toEqual([]);
    expect(exits(n("x", "branch", { cases: [{ when: "a" }, { when: "b" }] })).map((e) => e.handle))
      .toEqual(["case-0", "case-1", "else"]);
  });
});
