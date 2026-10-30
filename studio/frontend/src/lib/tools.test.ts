import { describe, expect, it } from "vitest";
import { fmtValue, newSlot, paramSlots, paramsOut, parseValue, returnSlots, returnsOut, slotProblem, slotProblems, valueProblem } from "./tools";

describe("tool params as a form", () => {
  it("reads the old list as untyped rows and writes it back as the list", () => {
    const s = paramSlots(["amount", "grade"]);
    expect(s.map((x) => [x.name, x.type, x.required])).toEqual([["amount", "", true], ["grade", "", true]]);
    expect(paramsOut(s)).toEqual(["amount", "grade"]);
  });

  it("round-trips the typed map of the shipped files", () => {
    const body = { account_last4: { type: "digits", length: 4 }, amount: "number", note: { type: "text", required: false },
                   grade: { type: "choice", choices: ["gold", "basic"] } };
    expect(paramsOut(paramSlots(body))).toEqual(body);
    expect(returnsOut(returnSlots({ balance: "number", ok: "boolean" }))).toEqual({ balance: "number", ok: "boolean" });
    expect(returnsOut([])).toBeUndefined();
  });

  it("says what blocks a save", () => {
    const typed = { ...newSlot("digits"), name: "a" };
    expect(slotProblems([typed, { ...newSlot(""), name: "b" }], [])).toMatch("모두 정하거나");
    expect(slotProblems([{ ...newSlot("choice"), name: "g" }], [])).toMatch("보기");
    expect(slotProblems([{ ...typed, length: "0" }], [])).toMatch("자릿수");
    expect(slotProblems([typed, { ...typed }], [])).toMatch("같은 이름");
    expect(slotProblems([{ ...newSlot(""), name: "x", required: false }], [])).toMatch("선택 속성");
    expect(slotProblems([typed], [{ ...newSlot("number"), name: "" }])).toMatch("이름");
    expect(slotProblems([typed], [{ ...newSlot("boolean"), name: "ok" }])).toBeNull();
    expect(slotProblem([{ ...typed, name: "1a" }], 0, "params")).toMatch("숫자로 시작");
  });
});

describe("fake API values follow the declared type", () => {
  const digits = { ...newSlot("digits"), name: "n", length: "4" };
  it("keeps digits as text and numbers as numbers", () => {
    expect(parseValue(digits, "0042")).toBe("0042");
    expect(parseValue({ ...newSlot("number"), name: "a" }, "12.5")).toBe(12.5);
    expect(parseValue({ ...newSlot("boolean"), name: "a" }, "true")).toBe(true);
    expect(parseValue(undefined, "4821")).toBe(4821);   // untyped: the old reading
    expect(fmtValue(digits, "0042")).toBe("0042");
    expect(fmtValue({ ...newSlot("boolean"), name: "a" }, false)).toBe("false");
  });
  it("tests a value the way the engine does", () => {
    expect(valueProblem(digits, "12a")).toMatch("숫자만");
    expect(valueProblem(digits, "123")).toMatch("4자리");
    expect(valueProblem(digits, "1234")).toBeNull();
    expect(valueProblem({ ...newSlot("choice"), choices: ["gold"] }, "silver")).toMatch("보기");
    expect(valueProblem({ ...newSlot("number"), name: "n" }, "x")).toMatch("숫자");
    expect(valueProblem(undefined, "anything")).toBeNull();
  });
});
