/** Names users see for engine terms. Internal names (flow, node id, slot, trigger) appear only in "개발 정보". */
import type { Bot } from "./api";

export const LANG: Record<string, string> = { ko: "한국어", en: "영어" };
export const DOMAIN: Record<string, string> = { bank: "은행", shop: "쇼핑몰", telecom: "통신사" };

export const langName = (l: string) => LANG[l] ?? l;
/** The business name: the Korean name of a repository domain, else the name given when it was made in the studio. */
export const domainName = (d: string, title?: string) => DOMAIN[d] ?? (title || d);

/** The bot's own name; imported bots are called "bank (ko)" until renamed, which reads better as "은행 상담봇". */
export function botName(b: Pick<Bot, "title" | "domain" | "lang">): string {
  if (b.title === `${b.domain} (${b.lang})`) return `${domainName(b.domain, (b as Partial<Bot>).domain_title)} 상담봇`;
  return b.title;
}

export type StatusTone = "ok" | "warn" | "err" | "idle";
/** One status per bot, in the order the user has to act: problems, then not checked, then not published. */
export function botStatus(b: Bot): { tone: StatusTone; text: string } {
  if (b.validated && !b.valid) return { tone: "err", text: "고칠 곳이 있어요" };
  if (b.has_unpublished_changes && !b.validated) return { tone: "warn", text: "검증이 필요해요" };
  if (b.has_unpublished_changes) return { tone: "warn", text: "게시하지 않은 변경" };
  if (!b.last_published_number) return { tone: "idle", text: "게시한 적 없음" };
  return { tone: "ok", text: "게시됨" };
}

export const ON_EXCEED = { handoff: "상담사에게 연결", end_call: "통화 종료" } as const;

export const EXTRACTORS: Record<string, string> = {
  text: "말 그대로", number: "숫자", digits: "숫자 자리(키패드 포함)", choice: "보기 중 하나", date: "날짜",
  month_start: "달의 첫날", day: "날짜의 일", time_window: "시간대(오전·오후·저녁)", duration: "기간",
};

export function when(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const time = d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `오늘 ${time}`;
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${time}`;
}
