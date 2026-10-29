import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ChatTest from "./ChatTest";

const BOT = {
  slug: "bank-ko", domain: "bank", lang: "ko", title: "bank (ko)", draft_revision: 3, shared_revision: 2,
  last_published_number: 0, has_unpublished_changes: true, validated: true, valid: true,
};
const TURN = {
  reply: "예약 번호는 BV1001입니다.", actions: [], before: { flow: "book_visit", node: "same_person" },
  after: { flow: "book_visit", node: "say_done" }, attributes: { "booker.phone_last4": "5580", "visitor.phone_last4": "5580" },
  changed: ["visitor.phone_last4"], meta: { ask_misses: 0 }, trace: { role_default: { role: "visitor", from: "booker" } }, stale: false,
  calls: [{ tool: "book_visit", args: { booker_phone: "5580", visitor_phone: "5580" }, ok: true, data: { reference: "BV1001" }, error: null,
            step: { node: "call", bind: { visitor_phone: { role: "visitor", field: "phone_last4" }, booker_phone: { const: "5580" } }, args: {} } }],
};
let posted: any[] = [];

beforeEach(() => {
  posted = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") posted.push([url, JSON.parse(String(init.body))]);
    const body = url.endsWith("/chat") ? { id: "s1", draft_revision: 3, shared_revision: 2, stale: false, buttons: [],
                                           labels: { "visitor.phone_last4": "방문자의 휴대폰 번호 끝 네 자리" } }
      : url.endsWith("/turns") ? TURN : null;
    return new Response(body === null ? null : JSON.stringify(body), { status: body === null ? 204 : 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("대화로 테스트", () => {
  it("sends a turn and shows what happened in it, in the 속성 terms", async () => {
    render(<ChatTest bot={BOT} onClose={() => {}} />);
    const box = await screen.findByLabelText("고객이 하는 말");
    await waitFor(() => expect((box as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(box, { target: { value: "네" } });
    fireEvent.submit(box.closest("form")!);
    expect(await screen.findByText("예약 번호는 BV1001입니다.")).toBeTruthy();
    expect(posted.at(-1)).toEqual(["/api/v1/bots/bank-ko/chat/s1/turns", { kind: "text", text: "네" }]);
    fireEvent.click(screen.getByRole("button", { name: /이 턴에서 일어난 일/ }));
    expect(screen.getByText("방문자의 휴대폰 번호 끝 네 자리")).toBeTruthy();
    expect(screen.getByText("수집한 속성")).toBeTruthy();
    expect(screen.getByText("넘긴 속성")).toBeTruthy();
    expect(screen.getByText(/← 고정값/)).toBeTruthy();
  });

  it("says why it cannot run before validation passes", () => {
    render(<ChatTest bot={{ ...BOT, validated: false, valid: false }} onClose={() => {}} />);
    expect(screen.getByText("검증한 뒤에 대화해 볼 수 있어요")).toBeTruthy();
    expect(screen.queryByLabelText("고객이 하는 말")).toBeNull();
  });
});
