// Regression: a redirect inside a splat route ("*") must not append to the URL. React Router v7 resolves a relative
// `to` against the whole matched URL there, so `<Navigate to="home">` at /mock/api gave /mock/api/home/home/...
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { paths } from "./paths";

const BOT = {
  slug: "bank-ko", domain: "bank", lang: "ko", title: "bank (ko)", draft_revision: 1, shared_revision: 1,
  last_published_number: 0, has_unpublished_changes: true, validated: false, valid: false,
};

let where = "";
let moves = 0;
/** Records the location; a redirect loop is cut after 10 moves so the test fails instead of hanging. */
function Spy() {
  const p = useLocation().pathname;
  if (p !== where) { moves += 1; where = p; }
  if (moves > 10) throw new Error(`redirect loop, now at ${p}`);
  return null;
}

async function land(path: string, expected: string): Promise<void> {
  where = ""; moves = 0;
  render(<MemoryRouter initialEntries={[path]}><App /><Spy /></MemoryRouter>);
  // lazy chunks, fetches and redirects settle; then the address must have stopped moving
  await waitFor(() => expect(where).toBe(expected), { timeout: 3000 });
  await act(async () => { await new Promise((r) => setTimeout(r, 100)); });
  expect(where).toBe(expected);
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const a = { on_exceed: "handoff" };
    const settings = { slug: "bank-ko", title: BOT.title, lang: "ko", domain: "bank", revision: 1, has_config_file: true,
      engine: { fallback: { max_misses: 3, ...a }, ask: { max_reprompts: 2, ...a }, switch: { max_parked: 2 },
                correction: { max_corrections: 2, ...a }, verification: { max_attempts: 3, ...a }, tools: { max_failures: 2, timeout_ms: 5000, ...a } },
      studio_only: { handoff_number: null, policy: {} }, policy_refs: [] };
    const body = url.endsWith("/api/v1/bots") ? [BOT]
      : url.endsWith("/bots/bank-ko") ? { ...BOT, counts: { faq: 0, flows: 0, tools: 0 } }
      : url.endsWith("/settings") ? settings
      : url.endsWith("/validation") ? null
      : url.endsWith("/types") ? { domain: "bank", exists: false, revision: 0, body: { types: {}, roles: {} }, usage: {}, field_types: ["text"], affects_bots: ["bank-ko"] }
      : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("redirects never stack path segments", () => {
  it.each([
    ["/mock", "/mock/home"],
    ["/mock/api", "/mock/home"],
    ["/mock/api/home/home", "/mock/home"],
    ["/mock/history", "/mock/home"],
  ])("mock %s -> %s", async (from, to) => {
    await land(from, to);
  });

  it.each([
    ["/b/bank-ko", paths.bot("bank-ko")],
    ["/b/bank-ko/nope", paths.bot("bank-ko")],
    ["/b/bank-ko/nope/overview/overview", paths.bot("bank-ko")],
  ])("bot %s -> %s", async (from, to) => {
    await land(from, to);
  });
});

describe("menu links are absolute", () => {
  // the reported case: clicking a menu item (e.g. "API 연결") again and again grew the address
  it.each([
    ["/mock/home", ["API 연결", "자주 묻는 질문", "API 연결", "API 연결", "개요"], "/mock/home"],
    ["/b/bank-ko/overview", ["API 연결", "데이터", "API 연결", "데이터", "게시 이력", "데이터"], "/b/bank-ko/data"],
  ])("from %s, clicking %j ends at %s", async (start, clicks, end) => {
    const { findAllByText } = render(<MemoryRouter initialEntries={[start]}><App /><Spy /></MemoryRouter>);
    where = ""; moves = 0;
    for (const label of clicks) {
      const links = (await findAllByText(label, undefined, { timeout: 3000 })).map((el) => el.closest("a")).filter(Boolean) as HTMLAnchorElement[];
      expect(links.length).toBeGreaterThan(0);
      for (const a of links) expect(a.getAttribute("href")).toMatch(/^\/(mock|b)\/[^/]+(\/[^/]+)?$/);
      await act(async () => { links[0].click(); await new Promise((r) => setTimeout(r, 30)); });
      moves = 0;   // each click is one move; only redirects in between would count
    }
    await waitFor(() => expect(where).toBe(end), { timeout: 3000 });
  });
});
