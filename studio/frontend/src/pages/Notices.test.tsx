import type { ReactElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bot } from "../api";
import type { NoticesResponse, RulesResponse } from "../lib/wording";
import { ToastProvider } from "../ui";
import Notices from "./Notices";
import Rules from "./Rules";

const BOT: Bot = {
  slug: "bank-ko", domain: "bank", domain_title: "bank", lang: "ko", title: "bank (ko)", copied_from: null, to_translate: 0,
  draft_revision: 1, shared_revision: 1, last_published_number: 0, has_unpublished_changes: true, validated: false, valid: false,
};
const KEYS = ["fallback.miss", "readback", "correction.offer"];
const STARTER: Record<string, string> = { "fallback.miss": "다시 말씀해 주세요.", readback: "{value}요.", "correction.offer": "{value} 맞으세요?" };
const NOTICES: NoticesResponse = {
  slug: "bank-ko", lang: "ko", exists: true, revision: 2,
  notices: [{ id: "a", text: "첫째", applies_when: null }, { id: "b", text: "둘째", applies_when: "amount > 5" }],
  wording: { ...STARTER, "fallback.miss": "고친 문구" }, starter_wording: STARTER,
  meaning: Object.fromEntries(KEYS.map((k) => [k, `${k} 의미`])), placeholder_keys: ["readback", "correction.offer"],
  attributes: ["amount"], reserved: ["customer", "policy", "result", "slots"], to_translate: ["b"], used_by: { a: [], b: ["flow1"] },
};
const RULES: RulesResponse = {
  slug: "bank-ko", lang: "ko",
  kinds: {
    confirm: { exists: true, revision: 1, body: { yes_words: ["네"], no_words: ["아니요"] }, starter: null },
    commands: { exists: true, revision: 1, body: { cancel: { any_of: ["취소"] }, back: { any_of: ["뒤"] }, agent: { any_of: ["상담"] } }, starter: null },
    corrections: { exists: true, revision: 1, body: { correction: { any_of: ["아니"] } }, starter: null },
    confusions: { exists: true, revision: 1, body: { pairs: [[13, 30]] }, starter: null },
  },
};
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
let sent: { method: string; url: string; body: any }[] = [];
let putStatus = 200;

beforeEach(() => {
  sent = []; putStatus = 200;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    if (method !== "GET") sent.push({ method, url, body });
    if (url.endsWith("/check-expression")) return json({ ok: !/bad/.test(body.text), error: /bad/.test(body.text) ? "syntax error" : null, names: ["amount"] });
    if (url.endsWith("/rules/test")) return json({ lang: "ko", tokens: ["취소"], command: { matched: "cancel", ties: [] },
      confirm: { answer: "no", yes_words: [], no_words: ["아니요"], tokens: [] }, correction: { matched: false, score: null }, confusions: [] });
    if (method === "PUT" && url.endsWith("/notices")) {
      if (putStatus === 422) return json({ detail: { message: "invalid", problems: [{ field: "notices.b.applies_when", message: "엔진 거절" }] } }, 422);
      return json({ ...NOTICES, notices: body.notices, wording: body.wording, revision: 3, to_translate: [] });
    }
    if (method === "PUT") return json(RULES);
    if (url.endsWith("/notices")) return json(NOTICES);
    if (url.endsWith("/rules")) return json(RULES);
    return json({}, 404);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const page = (el: ReactElement) => render(<MemoryRouter><ToastProvider>{el}</ToastProvider></MemoryRouter>);
const save = () => screen.getByRole("button", { name: "저장" }) as HTMLButtonElement;

describe("안내 문구", () => {
  it("starts clean, becomes dirty on an edit and saves with the revision", async () => {
    page(<Notices bot={BOT} />);
    const first = await screen.findByDisplayValue("첫째");
    expect(save().disabled).toBe(true);
    fireEvent.change(first, { target: { value: "첫째 고침" } });
    expect(screen.getByText(/저장하지 않은 변경/)).toBeTruthy();
    fireEvent.click(save());
    await waitFor(() => expect(sent.find((s) => s.method === "PUT")?.body.revision).toBe(2));
    expect(sent[0].body.notices[0].text).toBe("첫째 고침");
    await waitFor(() => expect(screen.getByText(/모든 변경을 저장했어요/)).toBeTruthy());
  });

  it("reorders with the buttons", async () => {
    page(<Notices bot={BOT} />);
    await screen.findByDisplayValue("첫째");
    fireEvent.click(screen.getAllByRole("button", { name: "아래로" })[0]);
    fireEvent.click(save());
    await waitFor(() => expect(sent[0].body.notices.map((n: any) => n.id)).toEqual(["b", "a"]));
  });

  it("shows the engine's check of a condition and which notices are still to translate", async () => {
    page(<Notices bot={BOT} />);
    expect(await screen.findByText("번역할 곳")).toBeTruthy();
    expect(await screen.findByText(/쓰는 속성: amount/)).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue("amount > 5"), { target: { value: "bad >" } });
    expect(await screen.findByText("syntax error")).toBeTruthy();
  });

  it("clicking an attribute puts its name into the condition", async () => {
    page(<Notices bot={BOT} />);
    await screen.findByDisplayValue("첫째");
    fireEvent.click(screen.getAllByRole("button", { name: "customer" })[0]);
    expect(screen.getByDisplayValue("customer")).toBeTruthy();
  });

  it("shows the server's message under the field on a 422", async () => {
    putStatus = 422;
    page(<Notices bot={BOT} />);
    fireEvent.change(await screen.findByDisplayValue("첫째"), { target: { value: "x" } });
    fireEvent.click(save());
    expect(await screen.findByText("엔진 거절")).toBeTruthy();
  });

  it("checks {value} in the wording tab and resets a key to the starter", async () => {
    page(<Notices bot={BOT} />);
    fireEvent.click(await screen.findByRole("button", { name: /상황별 문구/ }));
    const box = screen.getByLabelText("readback 문구") as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "읽어 드릴게요" } });
    expect(screen.getByText(/\{value\}가 들어가야 해요/)).toBeTruthy();
    expect(save().disabled).toBe(true);
    fireEvent.click(screen.getAllByRole("button", { name: "기본 문구로 되돌리기" })[1]);
    expect(screen.queryByText(/\{value\}가 들어가야 해요/)).toBeNull();
  });
});

describe("응답 규칙", () => {
  it("saves only the file that changed", async () => {
    page(<Rules bot={BOT} />);
    const yes = await screen.findByLabelText("예 단어");
    fireEvent.change(yes, { target: { value: "좋아요" } });
    fireEvent.keyDown(yes, { key: "Enter" });
    fireEvent.click(save());
    await waitFor(() => expect(sent.filter((s) => s.method === "PUT").map((s) => s.url)).toEqual(["/api/v1/bots/bank-ko/rules/confirm"]));
    expect(sent[0].body.body.yes_words).toEqual(["네", "좋아요"]);
  });

  it("refuses a word in both lists", async () => {
    page(<Rules bot={BOT} />);
    const no = await screen.findByLabelText("아니요 단어");
    fireEvent.change(no, { target: { value: "네" } });
    fireEvent.keyDown(no, { key: "Enter" });
    expect(screen.getByText(/모두 있는 단어/)).toBeTruthy();
    expect(save().disabled).toBe(true);
  });

  it("tries a sentence with the words on screen", async () => {
    page(<Rules bot={BOT} />);
    fireEvent.change(await screen.findByLabelText("시험할 말"), { target: { value: "취소할게요" } });
    fireEvent.click(screen.getByRole("button", { name: "확인" }));
    expect(await screen.findByText("엔진이 읽은 말")).toBeTruthy();
    expect(screen.getAllByText("취소").length).toBeGreaterThan(1);   // the token and the command
    const call = sent.find((s) => s.url.endsWith("/rules/test"))!;
    expect(call.body.text).toBe("취소할게요");
    expect(Object.keys(call.body.bodies).sort()).toEqual(["commands", "confirm", "confusions", "corrections"]);
  });
});
