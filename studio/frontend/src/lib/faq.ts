import type { Faq, Pattern } from "../api";

/** Guidance numbers from the dataset rules; the engine itself only refuses an entry without a pattern. */
export const MIN_PARAPHRASES = 3;
export const MIN_ASR = 1;

export interface FaqDraft {
  id: string; question: string; answer: string; paraphrases: string[]; asr: string[];
  allOf: string[][]; anyOf: string[]; noneOf: string[]; priority: string; regex: string[];
  /** other pattern keys (e.g. note) are kept as they were */
  rest: Record<string, unknown>; revision: number | null;
}

export function toDraft(e: Faq | null, newId = ""): FaqDraft {
  const { all_of, any_of, none_of, priority, regex, ...rest } = e?.pattern ?? {};
  return {
    id: e?.id ?? newId, question: e?.question ?? "", answer: e?.answer ?? "",
    paraphrases: e?.paraphrases ?? [], asr: e?.asr_variants ?? [],
    allOf: (all_of ?? []).map((g: any) => (Array.isArray(g) ? g.map(String) : [String(g)])),
    anyOf: any_of ?? [], noneOf: none_of ?? [], priority: priority === undefined ? "" : String(priority),
    regex: regex ?? [], rest, revision: e?.revision ?? null,
  };
}

export function toPattern(d: FaqDraft): Pattern {
  const p: Pattern = { ...(d.rest as Pattern) };
  const groups = d.allOf.filter((g) => g.length);
  if (groups.length) p.all_of = groups;
  if (d.anyOf.length) p.any_of = d.anyOf;
  if (d.noneOf.length) p.none_of = d.noneOf;
  if (d.priority.trim() !== "") p.priority = Number(d.priority);
  if (d.regex.length) p.regex = d.regex;
  return p;
}

export function toBody(d: FaqDraft) {
  return { id: d.id.trim(), question: d.question.trim(), answer: d.answer.trim(), paraphrases: d.paraphrases,
           asr_variants: d.asr, pattern: toPattern(d), revision: d.revision };
}

/** The matching rule in one Korean sentence. */
export function readPattern(p: Pattern | null | undefined): string {
  if (!p || (!p.all_of?.length && !p.any_of?.length && !p.regex?.length)) return "아직 조건이 없어요. 조건이 없으면 엔진이 받아들이지 않아요.";
  const parts: string[] = [];
  (p.all_of ?? []).forEach((g) => parts.push(`[${(Array.isArray(g) ? g : [g]).join("/")}]`));
  let s = parts.length ? `${parts.join(", ")}에서 각각 한 단어 이상 들어 있고` : "";
  if (p.any_of?.length) s += `${s ? " " : ""}[${p.any_of.join("/")}] 중 한 단어가 들어 있고`;
  if (p.regex?.length) s += `${s ? " " : ""}정규식 ${p.regex.length}개 중 하나가 맞고`;
  s = s.replace(/고$/, "으면 이 답변을 해요");
  if (p.none_of?.length) s += `. 단, [${p.none_of.join("/")}] 중 하나라도 있으면 제외해요`;
  return s + ".";
}

export type Problem = { field: "question" | "answer" | "pattern" | "paraphrases" | "asr" | "id"; text: string };

/** What still needs attention, in the order the form shows the fields. */
export function problems(d: FaqDraft, ids: string[] = [], isNew = false): Problem[] {
  const out: Problem[] = [];
  if (isNew && !/^[\w.]+$/.test(d.id)) out.push({ field: "id", text: "영문, 숫자, 점, 밑줄만 쓸 수 있어요" });
  if (isNew && ids.includes(d.id)) out.push({ field: "id", text: "이미 있는 이름이에요" });
  if (!d.question.trim()) out.push({ field: "question", text: "고객이 묻는 말을 적어 주세요" });
  if (!d.answer.trim()) out.push({ field: "answer", text: "봇이 할 답변을 적어 주세요" });
  const p = toPattern(d);
  if (!p.all_of?.length && !p.any_of?.length && !p.regex?.length) out.push({ field: "pattern", text: "알아듣는 조건을 하나 이상 넣어 주세요" });
  if (d.paraphrases.length < MIN_PARAPHRASES) out.push({ field: "paraphrases", text: `같은 뜻의 다른 말을 ${MIN_PARAPHRASES}개 이상 넣어 주세요` });
  if (d.asr.length < MIN_ASR) out.push({ field: "asr", text: "잘못 알아들은 예시를 1개 이상 넣어 주세요" });
  return out;
}

export function needsAttention(e: Faq): boolean {
  const d = toDraft(e);
  return problems(d).some((p) => p.field !== "id");
}
