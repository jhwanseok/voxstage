import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bot } from "../api";
import { ToastProvider } from "../ui";
import Tools, { paramSummary, ruleProblems } from "./Tools";

const BOT: Bot = {
  slug: "bank-ko", domain: "bank", domain_title: "bank", lang: "ko", title: "bank (ko)", copied_from: null, to_translate: 0,
  draft_revision: 1, shared_revision: 1, last_published_number: 0, has_unpublished_changes: true, validated: false, valid: false,
};
const BALANCE = {
  name: "get_balance", position: 0, revision: 3,
  body: { retry: 1, requires: "verified", params: { account_last4: { type: "digits", length: 4 }, note: { type: "text", required: false } },
          returns: { balance: "number", currency: "text" }, rules: [{ when: { account_last4: "4821" }, return: { balance: 1250, currency: "USD" } }], default: { error: "not_found" } },
};
let puts: any[] = [];

beforeEach(() => {
  puts = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "PUT") { puts.push([url, JSON.parse(String(init.body))]); return new Response(JSON.stringify({ ...BALANCE, affects_bots: ["bank-ko"], used_by_flows: [] }), { status: 200 }); }
    return new Response(JSON.stringify([BALANCE]), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const open = () => render(<MemoryRouter><ToastProvider><Tools bot={BOT} /></ToastProvider></MemoryRouter>);

describe("API 연결 with typed attributes", () => {
  it("lists the attributes with their types", () => {
    expect(paramSummary(BALANCE.body)).toBe("account_last4 (숫자 자리(키패드 포함) 4자리), note (말 그대로), 선택");
  });

  it("opens a typed tool as it is, and a save keeps the types and writes a digits value as text", async () => {
    open();
    fireEvent.click(await screen.findByRole("button", { name: /get_balance/ }));
    expect((screen.getByLabelText("받는 속성 1 형식") as HTMLSelectElement).value).toBe("digits");
    expect((screen.getByLabelText("받는 속성 1 이름") as HTMLInputElement).value).toBe("account_last4");
    expect(screen.getByLabelText("응답 항목 1 이름")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /가짜 API 응답 규칙/ }));
    fireEvent.click(screen.getByRole("button", { name: "규칙 추가" }));
    fireEvent.click(screen.getAllByRole("button", { name: "조건 추가" })[1]);
    fireEvent.change(screen.getByLabelText("규칙 2 조건 1 이름"), { target: { value: "account_last4" } });
    fireEvent.change(screen.getByLabelText("규칙 2 조건 1 값"), { target: { value: "0042" } });
    fireEvent.click(screen.getAllByRole("button", { name: "돌려줄 항목 추가" })[1]);
    fireEvent.change(screen.getByLabelText("규칙 2 응답 1 이름"), { target: { value: "balance" } });
    fireEvent.change(screen.getByLabelText("규칙 2 응답 1 값"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    const body = puts[0][1].body;
    expect(body.params).toEqual(BALANCE.body.params);
    expect(body.returns).toEqual(BALANCE.body.returns);
    expect(body.rules[1]).toEqual({ when: { account_last4: "0042" }, return: { balance: 75 } });
    expect(body.rules[0]).toEqual(BALANCE.body.rules[0]);
  });

  it("refuses a save while a rule names something the API does not declare", async () => {
    open();
    fireEvent.click(await screen.findByRole("button", { name: /get_balance/ }));
    fireEvent.change(screen.getByLabelText("받는 속성 1 이름"), { target: { value: "acct" } });
    expect(screen.getByText(/account_last4은\(는\) 받는 속성에 없어요/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("rule problems", () => {
  it("checks names and typed values the way the engine does", () => {
    const slot = (name: string, type: string, extra = {}) => ({ name, type, length: "", choices: [] as string[], required: true, ...extra });
    const d: any = { params: [slot("n", "digits", { length: "4" })], returns: [slot("fee", "number")], def: null,
                     rules: [{ when: [["n", "12"]], kind: "return", ret: [["fee", "x"], ["tax", "1"]], error: "", delay: "" }] };
    expect(ruleProblems(d)).toEqual(["규칙 1, n: 4자리로 넣어 주세요", "규칙 1, fee: 숫자를 넣어 주세요", "규칙 1: tax은(는) 응답 항목에 없어요"]);
  });
});
