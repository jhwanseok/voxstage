import { describe, expect, it } from "vitest";
import {
  bindingOf, callsBefore, fieldOptions, fieldOut, fieldSpec, fits, paramNames, renameRoleRefs, setBinding, withLabel,
  type TypesDoc,
} from "./datatypes";
import { renameNode, type FlowDraft } from "./flowEdit";

const DOC: TypesDoc = {
  types: { Person: { label: { ko: "사람" }, fields: { name: { type: "text", label: { ko: "이름" } }, last4: { type: "digits", length: 4 } } } },
  roles: { caller: { type: "Person", scope: "session", label: { ko: "전화 건 사람" } } },
};

describe("file shapes", () => {
  it("keeps the short field form when only the type is set", () => {
    expect(fieldSpec("text")).toEqual({ type: "text" });
    expect(fieldOut({ type: "text", length: undefined, label: {} })).toBe("text");
    expect(fieldOut({ type: "digits", length: 4 })).toEqual({ type: "digits", length: 4 });
  });
  it("sets one language's label and keeps the others", () => {
    expect(withLabel({ label: { en: "Booker" } }, "ko", "예약자")).toEqual({ label: { en: "Booker", ko: "예약자" } });
    expect(withLabel({ label: { ko: "예약자" } }, "ko", "")).toEqual({});
  });
  it("reads tool params as a list or a map", () => {
    expect(paramNames({ params: ["a", "b"] })).toEqual(["a", "b"]);
    expect(paramNames({ params: { a: { type: "digits" } } })).toEqual(["a"]);
    expect(paramNames(undefined)).toEqual([]);
  });
});

describe("binding", () => {
  it("lists role fields with readable names, flow roles first", () => {
    const opts = fieldOptions({ roles: { booker: { type: "Person", label: { ko: "예약자" } } } }, DOC, "ko");
    expect(opts.map((o) => o.label)).toEqual(["예약자의 이름", "예약자의 last4", "전화 건 사람의 이름", "전화 건 사람의 last4"]);
  });
  it("offers only fields whose type fits a typed parameter", () => {
    expect(fits({ type: "digits", length: 4 }, { type: "digits", length: 4 })).toBe(true);
    expect(fits({ type: "digits", length: 4 }, { type: "digits", length: 6 })).toBe(false);
    expect(fits({ type: "digits" }, { type: "text" })).toBe(false);
    expect(fits(null, { type: "text" })).toBe(true);   // untyped params (before A2) accept any field
  });
  it("reads old template arguments and replaces them by a binding", () => {
    const n = { type: "call", tool: "t", args: { order_id: "{order_id}", size: "{size | default('')}" } };
    expect(bindingOf(n, "order_id")).toEqual({ kind: "legacy", slot: "order_id", text: "{order_id}" });
    expect(bindingOf(n, "size").kind).toBe("template");
    expect(bindingOf(n, "other").kind).toBe("none");
    const b = setBinding(n, "order_id", { role: "caller", field: "last4" });
    expect(b.args).toEqual({ size: "{size | default('')}" });
    expect(b.bind).toEqual({ order_id: { role: "caller", field: "last4" } });
    expect(bindingOf(b, "order_id")).toEqual({ kind: "role", role: "caller", field: "last4" });
    const c = setBinding(setBinding(b, "size", { const: "L" }), "order_id", null);
    expect(c.args).toBeUndefined();
    expect(c.bind).toEqual({ size: { const: "L" } });
  });
  it("follows renamed steps and roles", () => {
    const nodes = { pay: { type: "call", bind: { a: { call: "lookup", field: "id" }, b: { role: "booker", field: "name" } } },
                    ask: { type: "ask", role: "booker", field: "name" }, same: { type: "confirm", role_default: "booker" } };
    const renamed = renameNode({ start: "lookup", header: {}, order: ["lookup", ...Object.keys(nodes)], nodes: { lookup: { type: "call" }, ...nodes } }, "lookup", "find");
    expect(renamed.nodes.pay.bind.a).toEqual({ call: "find", field: "id" });
    const r = renameRoleRefs(nodes, "booker", "guest");
    expect([r.pay.bind.b.role, r.ask.role, r.same.role_default]).toEqual(["guest", "guest", "guest"]);
  });
});

describe("calls before a step", () => {
  // lookup -ok-> check -yes-> pay ; check -no-> other -next-> pay ; lookup -error-> fail -next-> pay
  const d: FlowDraft = {
    start: "lookup", header: {}, order: ["lookup", "check", "other", "probe", "fail", "pay"],
    nodes: {
      lookup: { type: "call", on_ok: "check", on_error: "fail" },
      check: { type: "confirm", on_yes: "pay", on_no: "other" },
      other: { type: "call", on_ok: "pay", on_error: "pay" },
      probe: { type: "say" },
      fail: { type: "say", next: "pay" },
      pay: { type: "call" },
    },
  };
  it("says which results exist on every path and which on some", () => {
    expect(callsBefore(d, "check")).toEqual({ always: ["lookup"], sometimes: [] });
    expect(callsBefore(d, "pay")).toEqual({ always: [], sometimes: ["lookup", "other"] });
  });
  it("has nothing for a step the start does not reach", () => {
    expect(callsBefore(d, "probe")).toEqual({ always: [], sometimes: [] });
  });
});
