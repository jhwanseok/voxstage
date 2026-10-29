import { describe, expect, it } from "vitest";
import { fmt, lines, parse, words } from "./values";

describe("values", () => {
  it("keeps strings that look like numbers as strings", () => {
    expect(parse(fmt("4821"))).toBe("4821");
    expect(parse(fmt(4821))).toBe(4821);
    expect(parse(fmt("USD"))).toBe("USD");
    expect(parse(fmt(true))).toBe(true);
    expect(fmt("0001")).toBe("0001"); // not valid JSON: shown bare, read back as a string
    expect(parse("0001")).toBe("0001");
  });
  it("splits lists", () => {
    expect(lines("a\n\n b \n")).toEqual(["a", "b"]);
    expect(words("x, y ,,z")).toEqual(["x", "y", "z"]);
  });
});

import { eul } from "../ui";
describe("eul", () => {
  it("picks 을 after a final consonant and 를 after a vowel", () => {
    expect(eul("질문 목록")).toBe("질문 목록을");
    expect(eul("시나리오")).toBe("시나리오를");
    expect(eul("검증 결과")).toBe("검증 결과를");
    expect(eul("API")).toBe("API을(를)");
  });
});
