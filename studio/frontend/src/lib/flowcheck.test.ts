import { describe, expect, it } from "vitest";
import type { Item } from "../api";
import { describeCheck, isCheck, pathMarks, type Names } from "./flowcheck";

const names: Names = {
  source: (role, field) => (role ? `${role === "booker" ? "예약자" : role}의 ${field === "phone_last4" ? "휴대폰 번호 끝 네 자리" : field}` : String(field)),
  step: (id) => id,
};
const item = (o: Partial<Item>): Item => ({ severity: "error", source: "engine", code: "unbound", file: "f", lang: "ko", flow_id: "book", node_id: "call", field: null, message: "x", ...o });

describe("call check sentences", () => {
  it("says each code in the screen's words", () => {
    expect(describeCheck(item({ code: "unbound", parameter: "visitor_phone" }), names)).toBe("visitor_phone: 꼭 필요한데 연결된 속성이 없어요");
    expect(describeCheck(item({ code: "unbound", parameter: "fee", field: "lookup.price" }), names)).toMatch("응답에 없는 항목(lookup.price)");
    expect(describeCheck(item({ code: "type_mismatch", parameter: "amount", role: "booker", field: "phone_last4" }), names))
      .toBe("amount: 연결한 속성(예약자의 휴대폰 번호 끝 네 자리)의 형식이 이 API가 받는 형식과 맞지 않아요");
    expect(describeCheck(item({ code: "not_collected", parameter: "amount", field: "amount", path: ["gate", "lookup"] }), names))
      .toBe("amount: 연결한 속성(amount)을 받지 않고 이 단계에 오는 길이 있어요. 그 길: gate → lookup");
  });
  it("knows which items are the call check", () => {
    expect(isCheck(item({ code: "FlowError" }))).toBe(false);
    expect(isCheck(item({ code: "not_collected" }))).toBe(true);
  });
  it("finds the steps and exits of a witness path", () => {
    const edges = [{ id: "gate:case-0", from: "gate", to: "ask" }, { id: "gate:else", from: "gate", to: "lookup" }, { id: "ask:next", from: "ask", to: "lookup" }];
    const m = pathMarks([item({ code: "not_collected", path: ["gate", "lookup"] })], edges);
    expect([...m.nodes].sort()).toEqual(["gate", "lookup"]);
    expect([...m.edges]).toEqual(["gate:else"]);
  });
});
