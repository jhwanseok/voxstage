import { describe, expect, it } from "vitest";
import { addNode, connect, edges, exits, localProblems, removeNode, renameNode, type FlowDraft } from "./flowEdit";

const transfer = (): FlowDraft => ({
  start: "ask_amount", header: { triggers: { any_of: ["이체"] } },
  order: ["ask_amount", "confirm", "make", "say_done", "say_fail", "done"],
  nodes: {
    ask_amount: { type: "ask", slot: "amount", prompt: "얼마요?", extractor: "number", next: "confirm" },
    confirm: { type: "confirm", prompt: "보낼까요?", on_yes: "make", on_no: "done" },
    make: { type: "call", tool: "make_transfer", args: {}, on_ok: "say_done", on_error: "say_fail" },
    say_done: { type: "say", text: "보냈어요", next: "done" },
    say_fail: { type: "say", text: "실패", next: "done" },
    done: { type: "end" },
  },
});

describe("flow editing", () => {
  it("lists exits like the engine: yes/no, ok/error, cases and else", () => {
    expect(exits({ type: "confirm", on_yes: "a" }).map((e) => [e.handle, e.target])).toEqual([["yes", "a"], ["no", null]]);
    expect(exits({ type: "branch", cases: [{ when: "x", next: "a" }], else: "b" }).map((e) => e.handle)).toEqual(["case-0", "else"]);
    expect(exits({ type: "end" })).toEqual([]);
  });

  it("the draft as given has no local problems and the backend's edge ids", () => {
    const d = transfer();
    expect(localProblems(d)).toEqual([]);
    expect(edges(d).map((e) => e.id)).toContain("make:error");
  });

  it("adds a step after the selected one when it has a free exit", () => {
    const d = connect(transfer(), "say_fail", "next", null);
    const { draft, id } = addNode(d, "say", "say_fail");
    expect(id).toBe("say_1");
    expect(draft.nodes.say_fail.next).toBe("say_1");
    expect(draft.order.at(-1)).toBe("say_1");
    expect(localProblems(draft).map((p) => p.node)).toEqual(["say_1"]);   // the new step does not lead on yet
  });

  it("removing a step clears every link to it and the start", () => {
    let d = removeNode(transfer(), "done");
    expect(d.nodes.confirm.on_no).toBeUndefined();
    expect(d.nodes.say_done.next).toBeUndefined();
    expect(localProblems(d).some((p) => p.text.includes("끝내기"))).toBe(true);
    d = removeNode(d, "ask_amount");
    expect(d.start).toBeNull();
  });

  it("connects and reconnects a branch case", () => {
    const d: FlowDraft = { start: "b", order: ["b", "x", "y"], header: {},
      nodes: { b: { type: "branch", cases: [{ when: "a > 1", next: "x" }], else: "x" }, x: { type: "end" }, y: { type: "end" } } };
    const d2 = connect(d, "b", "case-0", "y");
    expect(d2.nodes.b.cases[0]).toEqual({ when: "a > 1", next: "y" });
    expect(d.nodes.b.cases[0].next).toBe("x");   // the old draft is untouched
  });

  it("renames a step everywhere and refuses a bad or taken name", () => {
    const d = renameNode(transfer(), "confirm", "confirm_send");
    expect(d.nodes.ask_amount.next).toBe("confirm_send");
    expect(d.order[1]).toBe("confirm_send");
    expect(renameNode(transfer(), "confirm", "make")).toEqual(transfer());
    expect(renameNode(transfer(), "confirm", "1bad")).toEqual(transfer());
  });
});
