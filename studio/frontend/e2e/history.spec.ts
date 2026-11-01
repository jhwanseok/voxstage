import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ST2 end to end: import bank, edit an answer, validate, publish, edit again, publish, read the comparison, roll back to
// version 1, and check that the draft and the export directory equal version 1's own files.
const API = "/api/v1";
const EXPORT = path.resolve("../e2e/.out/exports/bank-ko");
const lf = (s: string) => s.replace(/\r\n/g, "\n");

function exported(): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else out[path.relative(EXPORT, p).split(path.sep).join("/")] = lf(fs.readFileSync(p, "utf-8"));
    }
  };
  walk(EXPORT);
  return out;
}

test("import, edit, publish twice, compare, roll back", async ({ page, request }) => {
  // import the bank domain from the home screen
  await page.goto("/");
  await page.getByRole("button", { name: /은행 가져오기/ }).first().click();
  await expect(page.getByText("bank-ko").or(page.getByText("한국어")).first()).toBeVisible();
  const faq = await (await request.get(`${API}/bots/bank-ko/faq`)).json();
  const first = faq[0];
  const original = first.answer as string;

  const editAnswer = async (answer: string) => {
    await page.goto("/b/bank-ko/faq");
    await page.getByText(first.question, { exact: false }).first().click();
    await page.getByLabel("봇의 답변").fill(answer);
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await expect(page.getByText(/저장했어요/).first()).toBeVisible();
    await page.keyboard.press("Escape");
  };
  const publish = async (note: string) => {
    await page.getByRole("button", { name: "검증하기" }).click();
    await page.getByRole("button", { name: "게시하기" }).first().click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/에서 바뀐 것|이번에 게시할 내용/)).toBeVisible();
    await dialog.getByLabel(/무엇을 바꿨나요/).fill(note);
    await dialog.getByRole("button", { name: "게시하기" }).click();
    await expect(page).toHaveURL(/\/history$/);
  };

  await editAnswer("첫 번째 게시 답변입니다.");
  await publish("첫 게시");
  await editAnswer("두 번째 게시 답변입니다.");
  await publish("두 번째 게시");

  // the history compares version 2 with version 1 by meaning, and shows the text under 자세히
  await page.getByRole("button", { name: /2번째 버전/ }).click();
  await expect(page.getByText("2번째 버전이 이전 버전과 다른 점")).toBeVisible();
  await expect(page.getByText(new RegExp(`바뀜: ${first.id}.*\\(답변\\)`))).toBeVisible();
  await page.getByRole("button", { name: /자세히/ }).click();
  await expect(page.getByText("+", { exact: false }).filter({ hasText: "두 번째 게시 답변입니다." }).first()).toBeVisible();

  // roll back to version 1
  const v1 = await (await request.get(`${API}/bots/bank-ko/publications/1`)).json();
  const v1Files: Record<string, string> = {};
  for (const f of v1.files) v1Files[f.path] = lf(await (await request.get(`${API}/bots/bank-ko/publications/1/files/${f.path}`)).text());
  await page.getByRole("button", { name: /1번째 버전/ }).click();
  await page.getByRole("button", { name: "이 버전으로 되돌리기" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "되돌리기" }).click();
  await expect(page.getByText(/1번째 버전으로 되돌렸어요 \(3번째 버전\)/)).toBeVisible();

  const pubs = await (await request.get(`${API}/bots/bank-ko/publications`)).json();
  expect(pubs.map((p: any) => [p.number, p.kind, p.restored_from_number])).toEqual([[3, "rollback", 1], [2, "publish", null], [1, "publish", null]]);
  expect((await (await request.get(`${API}/bots/bank-ko/faq`)).json())[0].answer).toBe("첫 번째 게시 답변입니다.");
  expect(original).not.toBe("첫 번째 게시 답변입니다.");
  const bot = await (await request.get(`${API}/bots/bank-ko`)).json();
  expect(bot.has_unpublished_changes).toBe(false);

  // the export directory (what the engine reads) holds exactly version 1's files
  const out = exported();
  const v3 = await (await request.get(`${API}/bots/bank-ko/publications/3`)).json();
  const v3Files: Record<string, string> = {};
  for (const f of v3.files) v3Files[f.path] = lf(await (await request.get(`${API}/bots/bank-ko/publications/3/files/${f.path}`)).text());
  const own = (m: Record<string, string>) => Object.fromEntries(Object.entries(m).filter(([k]) => k.startsWith("bank/ko/")));
  expect(own(v3Files)).toEqual(own(v1Files));
  expect(out).toEqual(v3Files);
});
