// Words for the comparison of two versions (ST2): the backend's summary by meaning and the sibling check, in plain Korean.

export interface Summary {
  faq: { added: { id: string; question?: string }[]; removed: { id: string; question?: string }[]; changed: { id: string; question?: string; fields: string[] }[] };
  flows: {
    added: string[]; removed: string[];
    changed: {
      id: string; steps_added: { id: string; type?: string }[]; steps_removed: { id: string; type?: string }[];
      steps_changed: { id: string; type?: string; fields: string[] }[];
      rewired: { step: string; handle: string; before: string | null; after: string | null }[];
      header: string[]; start: [string | null, string | null] | null;
    }[];
  };
  tools: { added: string[]; removed: string[]; changed: { name: string; fields: string[] }[] };
  settings: { kind: string; label: string; scope: string; path: string; status: string; keys: string[] }[];
  other: { path: string; status: string }[];
  empty: boolean;
}
export interface FileDiff { path: string; status: "added" | "removed" | "changed"; unified: string }
export interface Ref { kind: "publication" | "draft" | "none"; number: number | null }
export interface Comparison { base: Ref; target: Ref; files: FileDiff[]; summary: Summary }

export interface Difference { kind: string; step?: string; exit?: string; parameter?: string; here?: string | null; there?: string | null }
export interface SiblingWarning { flow: string; kind: "only_here" | "only_there" | "structure_differs"; difference?: Difference }
export interface SiblingCheck { siblings: { bot: string; lang: string; compared: number; warnings: SiblingWarning[] }[]; warning_count: number }

const FAQ_FIELDS: Record<string, string> = { question: "질문", answer: "답변", paraphrases: "비슷한 말", asr_variants: "음성 인식 변형", pattern: "인식 규칙" };
const STEP_FIELDS: Record<string, string> = {
  text: "문구", prompt: "질문 문구", tool: "API", args: "넘기는 속성", bind: "속성 연결", slot: "속성", extractor: "읽는 방식",
  choices: "선택지", cases: "조건", type: "종류", slots: "속성 목록", reprompt: "다시 묻는 문구",
};
const TOOL_FIELDS: Record<string, string> = {
  params: "받는 속성", returns: "응답 항목", rules: "가짜 API 응답 규칙", default: "기본 응답", retry: "재시도", requires: "필요한 조건",
  verifies: "확인 조건", delay_ms: "지연", timeout_ms: "제한 시간",
};
const HEADER_FIELDS: Record<string, string> = {
  triggers: "시작 조건", buttons: "버튼", role: "역할", roles: "속성 역할", captures: "미리 받는 속성", interrupts: "끼어들기", carry: "이어받기",
  prefill: "미리 채우기", verification: "본인 확인",
};
export const STEP_KIND: Record<string, string> = {
  say: "말하기", ask: "묻기", confirm: "확인", call: "API 호출", branch: "갈림길", notices: "안내", form: "입력 폼", goto: "이동", end: "끝",
};
const EXIT: Record<string, string> = { next: "다음", yes: "예", no: "아니요", ok: "성공", error: "실패", else: "그 밖의 경우" };

const names = (keys: string[], table: Record<string, string>) => keys.map((k) => table[k] ?? k).join(", ");
export const exitName = (h: string) => EXIT[h] ?? (h.startsWith("case-") ? `${Number(h.slice(5)) + 1}번째 조건` : h);
const stepName = (id: string, type?: string) => (type && STEP_KIND[type] ? `${id} (${STEP_KIND[type]})` : id);
const quoted = (q?: string) => (q ? ` "${q}"` : "");

export interface Group { title: string; lines: string[] }

/** The summary as groups of short lines; empty groups are left out. */
export function describe(s: Summary): Group[] {
  const groups: Group[] = [];
  const faq: string[] = [];
  for (const e of s.faq.added) faq.push(`추가: ${e.id}${quoted(e.question)}`);
  for (const e of s.faq.removed) faq.push(`삭제: ${e.id}${quoted(e.question)}`);
  for (const e of s.faq.changed) faq.push(`바뀜: ${e.id}${quoted(e.question)} (${names(e.fields, FAQ_FIELDS)})`);
  if (faq.length) groups.push({ title: "자주 묻는 질문", lines: faq });

  const flows: string[] = [];
  for (const id of s.flows.added) flows.push(`시나리오 추가: ${id}`);
  for (const id of s.flows.removed) flows.push(`시나리오 삭제: ${id}`);
  for (const f of s.flows.changed) {
    if (f.start) flows.push(`${f.id}: 첫 단계가 ${f.start[0] ?? "없음"}에서 ${f.start[1] ?? "없음"}(으)로 바뀜`);
    if (f.header.length) flows.push(`${f.id}: ${names(f.header, HEADER_FIELDS)} 바뀜`);
    for (const x of f.steps_added) flows.push(`${f.id}: 단계 추가 ${stepName(x.id, x.type)}`);
    for (const x of f.steps_removed) flows.push(`${f.id}: 단계 삭제 ${stepName(x.id, x.type)}`);
    for (const x of f.steps_changed) flows.push(`${f.id}: 단계 ${stepName(x.id, x.type)} 바뀜 (${names(x.fields, STEP_FIELDS)})`);
    for (const r of f.rewired) flows.push(`${f.id}: 단계 ${r.step}의 '${exitName(r.handle)}' 연결이 ${r.before ?? "없음"}에서 ${r.after ?? "없음"}(으)로 바뀜`);
  }
  if (flows.length) groups.push({ title: "시나리오", lines: flows });

  const tools: string[] = [];
  for (const n of s.tools.added) tools.push(`추가: ${n}`);
  for (const n of s.tools.removed) tools.push(`삭제: ${n}`);
  for (const t of s.tools.changed) tools.push(`바뀜: ${t.name} (${names(t.fields, TOOL_FIELDS)})`);
  if (tools.length) groups.push({ title: "API 연결 (업종 공통)", lines: tools });

  const set = s.settings.map((x) => {
    const what = { added: "새로 생김", removed: "없어짐", changed: "바뀜" }[x.status] ?? x.status;
    return `${x.label}${x.scope === "shared" ? " (업종 공통)" : ""}: ${what}${x.keys.length ? ` (${x.keys.join(", ")})` : ""}`;
  });
  if (set.length) groups.push({ title: "설정", lines: set });

  if (s.other.length) groups.push({ title: "그 밖의 파일", lines: s.other.map((o) => `${{ added: "추가", removed: "삭제", changed: "바뀜" }[o.status] ?? o.status}: ${o.path}`) });
  return groups;
}

/** How a sibling check warning reads. "이 봇" is the bot being checked, "다른 언어 봇" the one it is compared with. */
export function siblingText(w: SiblingWarning): string {
  if (w.kind === "only_here") return `시나리오 ${w.flow}: 이 봇에만 있어요`;
  if (w.kind === "only_there") return `시나리오 ${w.flow}: 다른 언어 봇에만 있어요`;
  const d = w.difference!;
  const pair = `이 봇 ${d.here ?? "없음"}, 다른 언어 봇 ${d.there ?? "없음"}`;
  const lead = `시나리오 ${w.flow}`;
  switch (d.kind) {
    case "start": return `${lead}: 첫 단계가 달라요 (${pair})`;
    case "step_only_here": return `${lead}: 단계 ${d.step}: 이 봇에만 있어요`;
    case "step_only_there": return `${lead}: 단계 ${d.step}: 다른 언어 봇에만 있어요`;
    case "step_kind": return `${lead}: 단계 ${d.step}의 종류가 달라요 (이 봇 ${STEP_KIND[d.here ?? ""] ?? d.here}, 다른 언어 봇 ${STEP_KIND[d.there ?? ""] ?? d.there})`;
    case "exit": return `${lead}: 단계 ${d.step}의 '${exitName(d.exit ?? "")}' 연결이 달라요 (${pair})`;
    case "tool": return `${lead}: 단계 ${d.step}: 부르는 API가 달라요 (${pair})`;
    case "binding": return `${lead}: 단계 ${d.step}의 ${d.parameter} 연결이 달라요 (${pair})`;
    case "attribute": return `${lead}: 단계 ${d.step}: 받는 속성이 달라요 (${pair})`;
    default: return `${lead}: 구조가 달라요`;
  }
}
