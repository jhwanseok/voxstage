import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Bot, Publication } from "../api";
import { describe as describeChanges, siblingText, type Comparison, type SiblingCheck, type Summary } from "../lib/changes";
import { ToastProvider } from "../ui";
import History, { compareTitle } from "./History";
import PublishDialog from "./PublishDialog";

const BOT: Bot = {
  slug: "bank-ko", domain: "bank", domain_title: "bank", lang: "ko", title: "bank (ko)", copied_from: null, to_translate: 0,
  draft_revision: 4, shared_revision: 1, last_published_number: 3, has_unpublished_changes: false, validated: true, valid: true,
};
const PUB = (number: number, extra: Partial<Publication> = {}): Publication => ({
  number, note: `메모 ${number}`, kind: "publish", published_by: null, published_at: "2026-11-01T09:00:00+00:00", content_hash: "x", ...extra,
});
const EMPTY: Summary = { faq: { added: [], removed: [], changed: [] }, flows: { added: [], removed: [], changed: [] },
  tools: { added: [], removed: [], changed: [] }, settings: [], other: [], empty: true };
const SOME: Summary = {
  ...EMPTY, empty: false,
  faq: { added: [{ id: "new_q", question: "새 질문" }], removed: [], changed: [{ id: "balance", question: "잔액", fields: ["answer"] }] },
  flows: { added: [], removed: [], changed: [{ id: "transfer", steps_added: [{ id: "say_sorry", type: "say" }], steps_removed: [], steps_changed: [],
    rewired: [{ step: "say_fail", handle: "next", before: "done", after: "say_sorry" }], header: [], start: null }] },
  tools: { added: [], removed: [], changed: [{ name: "get_balance", fields: ["retry"] }] },
};
const cmp = (summary: Summary, base: Comparison["base"] = { kind: "publication", number: 2 }): Comparison => ({
  base, target: { kind: "publication", number: 3 }, summary,
  files: summary.empty ? [] : [{ path: "bank/ko/faq.yaml", status: "changed", unified: "--- a/bank/ko/faq.yaml\n+++ b/bank/ko/faq.yaml\n@@ -1 +1 @@\n-old\n+new\n" }],
});

let posts: { url: string; body: any }[] = [];
let handlers: Record<string, () => Response> = {};
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  posts = []; handlers = {};
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posts.push({ url, body: JSON.parse(String(init.body)) });
      const h = handlers[Object.keys(handlers).find((k) => k.startsWith("POST ") && url.endsWith(k.slice(5))) ?? ""];
      return h ? h() : json(PUB(4, { kind: "rollback", restored_from_number: 2 }), 201);
    }
    const key = Object.keys(handlers).find((k) => k.startsWith("GET ") && url.endsWith(k.slice(4)));
    if (key) return handlers[key]();
    if (url.endsWith("/publications")) return json([PUB(3), PUB(2), PUB(1)]);
    if (/\/publications\/\d$/.test(url)) return json({ ...PUB(Number(url.slice(-1))), files: [{ path: "bank/ko/faq.yaml", size: 10 }] });
    if (url.includes("/diff")) return json(cmp(SOME));
    return json({}, 404);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("words for a comparison", () => {
  it("names what changed by meaning", () => {
    const g = describeChanges(SOME);
    expect(g.map((x) => x.title)).toEqual(["자주 묻는 질문", "시나리오", "API 연결 (업종 공통)"]);
    expect(g[0].lines).toEqual(['추가: new_q "새 질문"', '바뀜: balance "잔액" (답변)']);
    expect(g[1].lines).toEqual(["transfer: 단계 추가 say_sorry (말하기)", "transfer: 단계 say_fail의 '다음' 연결이 done에서 say_sorry(으)로 바뀜"]);
    expect(g[2].lines).toEqual(["바뀜: get_balance (재시도)"]);
  });

  it("reads sibling warnings with the first difference", () => {
    expect(siblingText({ flow: "transfer", kind: "only_here" })).toBe("시나리오 transfer: 이 봇에만 있어요");
    expect(siblingText({ flow: "transfer", kind: "structure_differs", difference: { kind: "exit", step: "a", exit: "yes", here: "b", there: "c" } }))
      .toBe("시나리오 transfer: 단계 a의 '예' 연결이 달라요 (이 봇 b, 다른 언어 봇 c)");
  });

  it("says what each comparison target means", () => {
    expect(compareTitle(3, "previous")).toBe("3번째 버전이 이전 버전과 다른 점");
    expect(compareTitle(3, "draft")).toBe("지금 초안을 3번째 버전으로 되돌리면 바뀌는 것");
    expect(compareTitle(3, "1")).toBe("1번째 버전에서 3번째 버전으로 가면 바뀌는 것");
  });
});

const openHistory = () => render(<MemoryRouter><ToastProvider><History bot={BOT} /></ToastProvider></MemoryRouter>);

describe("History", () => {
  it("shows the summary against the previous version first, the text under 자세히, and lets the user pick another target", async () => {
    openHistory();
    fireEvent.click(await screen.findByRole("button", { name: /2번째 버전/ }));
    expect(await screen.findByText("추가: new_q \"새 질문\"")).toBeTruthy();
    expect(screen.queryByText("+new")).toBeNull();                          // the text is hidden until opened
    fireEvent.click(screen.getByRole("button", { name: /자세히/ }));
    expect(screen.getByText("+new")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("비교 대상"), { target: { value: "draft" } });
    expect(await screen.findByText("지금 초안을 2번째 버전으로 되돌리면 바뀌는 것")).toBeTruthy();
  });

  it("marks a rollback version on the list and offers the rollback only on older versions", async () => {
    handlers["GET /publications"] = () => json([PUB(3, { kind: "rollback", restored_from_number: 1 }), PUB(2), PUB(1)]);
    openHistory();
    expect(await screen.findByText("1번째 버전으로 되돌림")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /3번째 버전/ }));
    await screen.findByText(/내보낸 파일/);
    expect(screen.queryByRole("button", { name: "이 버전으로 되돌리기" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /2번째 버전/ }));
    expect(await screen.findByRole("button", { name: "이 버전으로 되돌리기" })).toBeTruthy();
  });

  it("asks before throwing away unpublished draft changes, then rolls back with discard_draft", async () => {
    handlers["POST /bots/bank-ko/publications/2/rollback"] = (() => {
      let first = true;
      return () => { if (first) { first = false; return json({ code: "unpublished_changes", message: "m" }, 409); } return json(PUB(4, { kind: "rollback", restored_from_number: 2 }), 201); };
    })();
    openHistory();
    fireEvent.click(await screen.findByRole("button", { name: /2번째 버전/ }));
    fireEvent.click(await screen.findByRole("button", { name: "이 버전으로 되돌리기" }));
    expect(screen.getByText("업종 공통 파일은 되돌리지 않아요")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    expect(await screen.findByText("아직 게시하지 않은 초안의 변경이 있어요")).toBeTruthy();
    expect(posts[0].body).toEqual({ note: "2번째 버전으로 되돌림", discard_draft: false });
    fireEvent.click(screen.getByRole("button", { name: "초안을 버리고 되돌리기" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1].body.discard_draft).toBe(true);
  });

  it("tells why the engine refused a rollback", async () => {
    handlers["POST /bots/bank-ko/publications/2/rollback"] = () => json({ message: "validation failed", report: { ok: false, items: [
      { severity: "error", source: "engine", code: "x", file: "f", lang: "ko", flow_id: "transfer", node_id: null, field: null, message: "API가 없어요" }] } }, 422);
    openHistory();
    fireEvent.click(await screen.findByRole("button", { name: /2번째 버전/ }));
    fireEvent.click(await screen.findByRole("button", { name: "이 버전으로 되돌리기" }));
    fireEvent.click(screen.getByRole("button", { name: "되돌리기" }));
    expect(await screen.findByText(/지금의 공통 파일.*맞지 않아서 되돌리지 않았어요/)).toBeTruthy();
    expect(screen.getByText("API가 없어요")).toBeTruthy();
  });
});

describe("PublishDialog", () => {
  const open = () => render(<MemoryRouter><ToastProvider><PublishDialog bot={BOT} onClose={() => {}} /></ToastProvider></MemoryRouter>);
  const siblings = (n: number): SiblingCheck => ({ warning_count: n, siblings: [{ bot: "bank-en", lang: "en", compared: 5,
    warnings: n ? [{ flow: "transfer", kind: "only_here" }] : [] }] });

  it("shows what changed since the last version and the sibling warnings, which do not block", async () => {
    handlers["GET /changes"] = () => json(cmp(SOME, { kind: "publication", number: 3 }));
    handlers["GET /siblings/check"] = () => json(siblings(1));
    open();
    expect(await screen.findByText("3번째 버전에서 바뀐 것")).toBeTruthy();
    expect(screen.getByText('바뀜: balance "잔액" (답변)')).toBeTruthy();
    expect(await screen.findByText("다른 언어 봇과 구조가 달라요")).toBeTruthy();
    expect(screen.getByText("시나리오 transfer: 이 봇에만 있어요")).toBeTruthy();
    expect((screen.getByRole("button", { name: "게시하기" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("says before the note is typed that there is nothing to publish", async () => {
    handlers["GET /changes"] = () => json(cmp(EMPTY, { kind: "publication", number: 3 }));
    handlers["GET /siblings/check"] = () => json(siblings(0));
    open();
    expect(await screen.findByText("마지막 게시와 내용이 같아서 게시할 것이 없어요")).toBeTruthy();
    expect((screen.getByRole("button", { name: "게시하기" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("다른 언어 봇과 구조가 달라요")).toBeNull();
  });
});
