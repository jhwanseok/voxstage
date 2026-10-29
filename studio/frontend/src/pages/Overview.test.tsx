import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bot } from "../api";
import { DeleteBot } from "./Overview";

const BOT: Bot = {
  slug: "clinic-ko", domain: "clinic", domain_title: "병원 예약", lang: "ko", title: "병원 상담봇", copied_from: null, to_translate: 0,
  draft_revision: 1, shared_revision: 1, last_published_number: 1, has_unpublished_changes: false, validated: true, valid: true,
};
let calls: [string, string][] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push([init?.method ?? "GET", url]);
    if (init?.method === "DELETE") return new Response(JSON.stringify({ deleted: "clinic-ko", domain_deleted: "clinic" }), { status: 200 });
    return new Response(JSON.stringify({ faq: 3, flows: 2, publications: 1, last_of_domain: true, domain_tools: 4 }), { status: 200 });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("상담봇 삭제", () => {
  it("says what goes and deletes only after the name is typed", async () => {
    render(<MemoryRouter><DeleteBot bot={BOT} name="병원 상담봇" onClose={() => {}} /></MemoryRouter>);
    expect(await screen.findByText(/마지막 상담봇이라 업종도 함께 지워요/)).toBeTruthy();
    const del = screen.getByRole("button", { name: "삭제" }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/그대로 입력해 주세요/), { target: { value: "병원" } });
    expect(del.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/그대로 입력해 주세요/), { target: { value: "병원 상담봇" } });
    expect(del.disabled).toBe(false);
    fireEvent.click(del);
    await waitFor(() => expect(calls).toContainEqual(["DELETE", "/api/v1/bots/clinic-ko"]));
  });
});
