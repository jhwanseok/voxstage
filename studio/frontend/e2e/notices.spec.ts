import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

// ST3 end to end: edit one situation wording and add a fixed notice on 안내 문구, validate, publish, then check the export
// directory (what the engine reads) and a chat reply that says the new wording.
const API = "/api/v1";
const EXPORT = path.resolve("../e2e/.out/exports/bank-ko");

test("edit a wording and add a fixed notice, publish, and the engine says it", async ({ page, request }) => {
  const imp = await request.post(`${API}/domains/import`, { data: { domain: "bank", replace: true } });
  expect([201, 200]).toContain(imp.status());

  await page.goto("/b/bank-ko/notices");
  await page.getByRole("button", { name: /상황별 문구/ }).click();
  await page.getByLabel("fallback.miss 문구").fill("제가 잘 못 들었어요. 한 번만 더 말씀해 주세요.");
  // {value} is checked as it is typed
  await page.getByLabel("readback 문구").fill("읽어 드릴게요");
  await expect(page.getByText(/\{value\}가 들어가야 해요/)).toBeVisible();
  await expect(page.getByRole("button", { name: "저장", exact: true })).toBeDisabled();
  await page.getByLabel("readback 문구").fill("{value}입니다.");

  await page.getByRole("button", { name: /고정 안내/ }).first().click();
  await page.getByRole("button", { name: "고정 안내 추가" }).click();
  await page.getByLabel("읽어 줄 문구").last().fill("이 안내는 상담 품질을 위해 녹음됩니다.");
  await page.getByLabel("말하는 조건").last().fill("zzz_unknown > 1");
  await expect(page.getByText(/zzz_unknown/).first()).toBeVisible();     // the engine's own message under the box
  await page.getByLabel("말하는 조건").last().fill("");
  await page.getByRole("button", { name: "저장", exact: true }).click();
  await expect(page.getByText(/저장했어요/).first()).toBeVisible();

  await page.getByRole("button", { name: "검증하기" }).click();
  await page.getByRole("button", { name: "게시하기" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/무엇을 바꿨나요/).fill("안내 문구 바꿈");
  await dialog.getByRole("button", { name: "게시하기" }).click();
  await expect(page).toHaveURL(/\/history$/);

  // the export directory holds the new wording and the notice, with priorities 10 and 20
  const text = fs.readFileSync(path.join(EXPORT, "bank", "ko", "notices.yaml"), "utf-8");
  expect(text).toContain("제가 잘 못 들었어요. 한 번만 더 말씀해 주세요.");
  expect(text).toContain("이 안내는 상담 품질을 위해 녹음됩니다.");
  expect(text).toMatch(/priority: 20/);

  // and a chat reply that is the new wording
  const chat = await (await request.post(`${API}/bots/bank-ko/chat`, { data: {} })).json();
  const turn = await (await request.post(`${API}/bots/bank-ko/chat/${chat.id}/turns`, { data: { text: "ㅋㅋㅋㅋㅋ" } })).json();
  expect(turn.reply).toBe("제가 잘 못 들었어요. 한 번만 더 말씀해 주세요.");
});
