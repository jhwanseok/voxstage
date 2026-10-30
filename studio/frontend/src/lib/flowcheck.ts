/** The engine's call check (R16b, ADR 0014 P1) as the editor shows it. The loader reports `unbound`, `type_mismatch` and
 *  `not_collected` with the node, the parameter, the source and, for `not_collected`, one witness path; this turns each into
 *  a sentence and finds the path's edges. The check itself runs only in the engine (validation), never here. */
import type { Item } from "../api";

export const CHECK_CODES = ["unbound", "type_mismatch", "not_collected"] as const;
export type CheckCode = (typeof CHECK_CODES)[number];
export const isCheck = (i: Pick<Item, "code">): boolean => (CHECK_CODES as readonly string[]).includes(i.code);

export interface Names {
  /** "예약자의 이름" for a role field, the slot's own name for a flat slot (role null) */
  source: (role: string | null | undefined, field: string | null | undefined) => string;
  /** "API 호출 (lookup)": how a step is called in a sentence */
  step: (id: string) => string;
}

/** One sentence per problem, in the words of the screen: 속성 for what a scenario collects, 연결 for a binding. */
export function describeCheck(i: Item, n: Names): string {
  const p = i.parameter ?? "";
  const src = n.source(i.role, i.field);
  switch (i.code) {
    case "unbound":
      return i.field ? `${p}: 앞 API의 응답에 없는 항목(${src})을 연결했어요` : `${p}: 꼭 필요한데 연결된 속성이 없어요`;
    case "type_mismatch":
      return `${p}: 연결한 속성(${src})의 형식이 이 API가 받는 형식과 맞지 않아요`;
    case "not_collected": {
      const path = (i.path ?? []).map(n.step).join(" → ");
      return `${p}: 연결한 속성(${src})을 받지 않고 이 단계에 오는 길이 있어요${path ? `. 그 길: ${path}` : ""}`;
    }
    default:
      return i.message;
  }
}

/** The steps and exits of the first witness path of `items`, so the canvas can mark them. */
export function pathMarks(items: Item[], edges: { id: string; from: string; to: string }[]): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>(), marked = new Set<string>();
  for (const i of items) {
    if (i.code !== "not_collected" || !i.path) continue;
    i.path.forEach((id) => nodes.add(id));
    for (let k = 0; k + 1 < i.path.length; k++) {
      const e = edges.find((x) => x.from === i.path![k] && x.to === i.path![k + 1]);
      if (e) marked.add(e.id);
    }
  }
  return { nodes, edges: marked };
}
