import { describe, expect, it } from "vitest";
import { freshId, insertName, move, NOTICE_ID, noticeTextProblem, pairProblem, valueProblem } from "./wording";

const KEYS = ["readback", "correction.offer"];

describe("{value} in wording", () => {
  it("is required where a value is read back", () => {
    expect(valueProblem("readback", "읽어 드릴게요", KEYS)).toMatch(/\{value\}/);
    expect(valueProblem("readback", "{value}요.", KEYS)).toBeNull();
    expect(valueProblem("correction.offer", "{value} 맞으세요?", KEYS)).toBeNull();
  });
  it("is refused everywhere else", () => {
    expect(valueProblem("fallback.miss", "{value}를 못 들었어요", KEYS)).toMatch(/쓸 수 없어요/);
    expect(valueProblem("fallback.miss", "다시 말씀해 주세요", KEYS)).toBeNull();
  });
  it("needs text", () => expect(valueProblem("fallback.miss", "  ", KEYS)).toBeTruthy());
});

describe("fixed notices", () => {
  it("are spoken as written, so no braces", () => {
    expect(noticeTextProblem("수수료가 있어요")).toBeNull();
    expect(noticeTextProblem("{x}")).toMatch(/기호/);
    expect(noticeTextProblem("")).toBeTruthy();
  });
  it("names start with a letter", () => {
    expect(NOTICE_ID.test("time_deposit-1")).toBe(true);
    expect(NOTICE_ID.test("1abc")).toBe(false);
    expect(NOTICE_ID.test("a b")).toBe(false);
  });
  it("move swaps neighbours and stays put at the ends", () => {
    expect(move(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(move(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
    const list = ["a", "b"];
    expect(move(list, 0, -1)).toBe(list);
  });
  it("a fresh name is not taken", () => expect(freshId(["notice_1", "notice_2"])).toBe("notice_3"));
  it("inserts an attribute name after the text", () => {
    expect(insertName("", "amount")).toBe("amount");
    expect(insertName("amount >", "pin")).toBe("amount > pin");
    expect(insertName("amount ", "pin")).toBe("amount pin");
  });
});

describe("confusable pairs", () => {
  it("accepts different whole numbers used once", () => expect(pairProblem([[13, 30], [14, 40]])).toBeNull());
  it("refuses an empty, equal or repeated number", () => {
    expect(pairProblem([[NaN, 30]])).toBeTruthy();
    expect(pairProblem([[13, 13]])).toMatch(/서로 다른/);
    expect(pairProblem([[13, 30], [30, 40]])).toMatch(/두 쌍/);
  });
});
