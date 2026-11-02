/** 안내 문구, 응답 규칙, 슬롯 목록 (ST3): shapes of the API and the small checks the forms run before the server does. */

export interface NoticeItem { id: string; text: string; applies_when: string | null }
export interface NoticesResponse {
  slug: string; lang: string; exists: boolean; revision: number;
  notices: NoticeItem[]; wording: Record<string, string>; starter_wording: Record<string, string>;
  meaning: Record<string, string>; placeholder_keys: string[]; attributes: string[]; reserved: string[];
  to_translate: string[]; used_by: Record<string, string[]>;
}
export interface ExpressionCheck { ok: boolean; error: string | null; names: string[] }
export interface Problem { field: string; message: string }

export interface PatternBody { any_of?: string[]; all_of?: (string | string[])[]; none_of?: string[]; regex?: string[]; priority?: number; note?: string }
export type RuleKind = "confirm" | "commands" | "corrections" | "confusions";
export interface RuleFile { exists: boolean; revision: number; body: Record<string, any>; starter: Record<string, any> | null }
export interface RulesResponse { slug: string; lang: string; kinds: Record<RuleKind, RuleFile> }
export interface RuleTest {
  lang: string; tokens: string[];
  command: { matched: string | null; ties: string[] };
  confirm: { answer: "yes" | "no" | "unclear"; yes_words: string[]; no_words: string[]; tokens: string[] };
  correction: { matched: boolean; score: number | null };
  confusions: { value: number; partner: number }[];
}

export interface SlotListsResponse {
  domain: string;
  sensitive: { revision: number; slots: string[] };
  readback: { revision: number; slots: { slot: string; format: string }[] };
  candidates: { sensitive: string[]; readback: string[] };
  formats: { call: string; label: string }[];
  asked_in: Record<string, string[]>;
  affects_bots: string[];
}

export const RULE_KINDS: RuleKind[] = ["confirm", "commands", "corrections", "confusions"];
export const COMMAND_NAMES: Record<string, string> = { cancel: "취소", back: "이전으로", agent: "상담사 연결" };

/** Why a wording text cannot be saved, or null. `{value}` belongs only to the keys that read a value back. */
export function valueProblem(key: string, text: string, placeholderKeys: string[]): string | null {
  if (!text.trim()) return "문구를 입력하세요.";
  const needs = placeholderKeys.includes(key);
  if (needs && !text.includes("{value}")) return "{value}가 들어가야 해요. 값이 들어갈 자리예요.";
  if (!needs && text.includes("{value}")) return "이 문구에는 {value}를 쓸 수 없어요.";
  return null;
}

/** Why a fixed notice's text cannot be saved, or null (spoken as written, so no braces). */
export function noticeTextProblem(text: string): string | null {
  if (!text.trim()) return "문구를 입력하세요.";
  if (/[{}]/.test(text)) return "고정 안내는 그대로 읽어요. { } 기호는 쓸 수 없어요.";
  return null;
}

export const NOTICE_ID = /^[A-Za-z][\w-]{0,59}$/;

/** Moves item `i` by `by` places (a new list; the same list when it cannot move). */
export function move<T>(list: T[], i: number, by: -1 | 1): T[] {
  const j = i + by;
  if (j < 0 || j >= list.length) return list;
  const out = [...list];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

/** A name not used yet, for "고정 안내 추가". */
export function freshId(taken: string[], base = "notice"): string {
  for (let n = 1; ; n++) { const id = `${base}_${n}`; if (!taken.includes(id)) return id; }
}

/** Appends an attribute name to an `applies_when` text, with a space when the text does not end in one. */
export function insertName(text: string, name: string): string {
  return text && !/\s$/.test(text) ? `${text} ${name}` : `${text}${name}`;
}

/** Pairs of confusable numbers as typed; a pair is ready when both are different whole numbers, none used twice. */
export function pairProblem(pairs: [number, number][]): string | null {
  const seen = new Set<number>();
  for (const [a, b] of pairs) {
    if (!Number.isInteger(a) || !Number.isInteger(b)) return "숫자 두 개를 모두 넣어 주세요.";
    if (a === b) return "서로 다른 숫자여야 해요.";
    for (const v of [a, b]) { if (seen.has(v)) return `${v}이(가) 두 쌍에 들어 있어요.`; seen.add(v); }
  }
  return null;
}
