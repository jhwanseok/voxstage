import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bot, Domain } from "../api";
import NewBot, { domainIdProblem, suggestId } from "./NewBot";

const bot = (domain: string, lang: string): Bot => ({
  slug: `${domain}-${lang}`, domain, domain_title: domain, lang, title: `${domain} (${lang})`, copied_from: null, to_translate: 0,
  draft_revision: 1, shared_revision: 1, last_published_number: 0, has_unpublished_changes: true, validated: false, valid: false,
});
const DOMAINS: Domain[] = [
  { slug: "bank", title: "bank", bots: [bot("bank", "en"), bot("bank", "ko")] },
  { slug: "clinic", title: "병원 예약", bots: [bot("clinic", "ko")] },
];
let posted: any[] = [];

beforeEach(() => {
  posted = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") posted.push([url, JSON.parse(String(init.body))]);
    const a = { on_exceed: "handoff" };
    const body = url.endsWith("/languages") ? ["en", "ko"]
      : url.endsWith("/settings") ? { engine: { ask: { max_reprompts: 1, ...a } }, studio_only: { handoff_number: "02-000-0000", policy: {} } }
      : url.endsWith("/bots") ? { ...bot("clinic", "en"), title: "병원 예약 상담봇", counts: { faq: 0, flows: 0, tools: 0 }, translate: { faq: [], flows: [], notices: [] } }
      : null;
    return new Response(JSON.stringify(body), { status: init?.method === "POST" ? 201 : 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const open = () => render(<MemoryRouter><NewBot domains={DOMAINS} inRepo={["shop"]} onClose={() => {}} /></MemoryRouter>);

describe("new business id", () => {
  it("is suggested from an ASCII name only", () => {
    expect(suggestId("Dental Care 2")).toBe("dental-care-2");
    expect(suggestId("병원 예약")).toBe("");
  });
  it("says what is wrong", () => {
    expect(domainIdProblem("", [], [])).toMatch("넣어 주세요");
    expect(domainIdProblem("Clinic", [], [])).toMatch("소문자");
    expect(domainIdProblem("bank", ["bank"], [])).toMatch("이미 있는 업종");
    expect(domainIdProblem("shop", [], ["shop"])).toMatch("가져오기");
    expect(domainIdProblem("clinic", ["bank"], ["shop"])).toBeNull();
  });
});

describe("새 상담봇", () => {
  it("disables languages the business already has", async () => {
    open();
    expect(await screen.findByText("이 업종은 모든 언어의 상담봇이 이미 있어요")).toBeTruthy();
    expect((screen.getByRole("button", { name: "만들기" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("copies the sibling with its defaults", async () => {
    open();
    fireEvent.change(screen.getByLabelText("업종"), { target: { value: "clinic" } });
    const copy = await screen.findByRole("radio", { name: /한국어 상담봇 복사/ });
    await waitFor(() => expect((screen.getByRole("radio", { name: /영어/ }) as HTMLInputElement).checked).toBe(true));
    fireEvent.click(copy);
    await waitFor(() => expect((screen.getByLabelText(/상담사 연결 번호/) as HTMLInputElement).value).toBe("02-000-0000"));
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual(["/api/v1/bots", {
      domain: "clinic", lang: "en", title: "병원 예약 상담봇", start: "copy", copy_from: "clinic-ko",
      settings: { engine: { ask: { max_reprompts: 1 } }, studio_only: { handoff_number: "02-000-0000" } },
    }]);
  });

  it("makes a new business with an empty bot", async () => {
    open();
    fireEvent.change(screen.getByLabelText("업종"), { target: { value: "__new__" } });
    fireEvent.change(screen.getByLabelText("업종 이름"), { target: { value: "Dental" } });
    expect((screen.getByLabelText("영문 ID") as HTMLInputElement).value).toBe("dental");
    expect((screen.getByRole("radio", { name: /다른 언어 상담봇 복사/ }) as HTMLInputElement).disabled).toBe(true);
    await waitFor(() => expect((screen.getByRole("button", { name: "만들기" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0][1]).toMatchObject({ domain: "dental", domain_title: "Dental", lang: "en", title: "Dental 상담봇", start: "empty" });
  });
});
