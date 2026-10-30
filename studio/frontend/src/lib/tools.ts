/** API 연결 (tools.yaml) as the form edits it: the typed params and the response items of ADR 0014 A2 (engine R16b),
 *  and the fake API rules that must keep to them (P6). The engine's loader has the last word; the checks here only keep
 *  the form from writing what it would refuse, and say why next to the row. */
import { fmt, parse } from "./values";

export const PARAM_TYPES = ["text", "digits", "number", "choice", "date", "month_start", "day", "time_window", "duration"] as const;
export const RETURN_TYPES = [...PARAM_TYPES, "boolean"] as const;

/** One received attribute (`params`) or one response item (`returns`). `type: ""` is an old untyped param. */
export interface Slot { name: string; type: string; length: string; choices: string[]; required: boolean }
export const newSlot = (type = "text"): Slot => ({ name: "", type, length: "", choices: [], required: true });

function fromSpec(name: string, v: unknown): Slot {
  const s = (typeof v === "string" ? { type: v } : v && typeof v === "object" ? v : {}) as Record<string, any>;
  return { name, type: s.type ?? "", length: s.length == null ? "" : String(s.length), choices: (s.choices ?? []).map(String), required: s.required !== false };
}

/** `params` is a list of names (untyped, all required) or a map of name -> type or spec. */
export function paramSlots(params: unknown): Slot[] {
  if (Array.isArray(params)) return params.map((n) => ({ ...newSlot(""), name: String(n) }));
  return params && typeof params === "object" ? Object.entries(params).map(([n, v]) => fromSpec(n, v)) : [];
}
export function returnSlots(returns: unknown): Slot[] {
  return returns && typeof returns === "object" && !Array.isArray(returns) ? Object.entries(returns).map(([n, v]) => fromSpec(n, v)) : [];
}

function specOut(s: Slot, withRequired: boolean): string | Record<string, unknown> {
  const o: Record<string, unknown> = { type: s.type };
  if (s.type === "digits" && s.length.trim() !== "") o.length = Number(s.length);
  if (s.type === "choice") o.choices = s.choices;
  if (withRequired && !s.required) o.required = false;
  return Object.keys(o).length === 1 ? s.type : o;
}

/** The file shape: the old list while no param has a type, the typed map as soon as one has (the engine takes the map
 *  only when every param is typed, see `slotProblems`). A bare type name stays a bare name, as in the shipped files. */
export function paramsOut(slots: Slot[]): string[] | Record<string, unknown> {
  const rows = slots.filter((s) => s.name.trim());
  if (rows.every((s) => !s.type)) return rows.map((s) => s.name.trim());
  return Object.fromEntries(rows.map((s) => [s.name.trim(), specOut(s, true)]));
}
export function returnsOut(slots: Slot[]): Record<string, unknown> | undefined {
  const rows = slots.filter((s) => s.name.trim());
  return rows.length ? Object.fromEntries(rows.map((s) => [s.name.trim(), specOut(s, false)])) : undefined;
}

const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const dup = (slots: Slot[], i: number) => slots.some((o, j) => j !== i && o.name.trim() === slots[i].name.trim());

/** What is wrong with one row, in words for the person who fills the form; null when it is fine. */
export function slotProblem(slots: Slot[], i: number, kind: "params" | "returns"): string | null {
  const s = slots[i];
  if (!s.name.trim()) return "이름을 넣어 주세요";
  if (!NAME.test(s.name.trim())) return "영어, 숫자, 밑줄만 쓸 수 있고 숫자로 시작할 수 없어요";
  if (dup(slots, i)) return "같은 이름이 있어요";
  if (s.type === "digits" && s.length.trim() !== "" && !/^[1-9]\d*$/.test(s.length.trim())) return "자릿수는 1 이상의 정수예요";
  if (s.type === "choice" && !s.choices.length) return "보기를 하나 이상 넣어 주세요";
  if (kind === "params" && !s.type && !s.required) return "선택 속성은 형식을 정해야 해요";
  return null;
}

/** The first thing that stops a save, or null. Typed params are all-or-nothing: the engine reads the map form only. */
export function slotProblems(params: Slot[], returns: Slot[]): string | null {
  if (params.some((s) => s.type) && params.some((s) => !s.type)) return "받는 속성의 형식을 모두 정하거나 모두 비워 주세요";
  for (let i = 0; i < params.length; i++) {
    const p = slotProblem(params, i, "params");
    if (p) return `받는 속성 ${params[i].name || i + 1}: ${p}`;
  }
  for (let i = 0; i < returns.length; i++) {
    const p = slotProblem(returns, i, "returns");
    if (p) return `응답 항목 ${returns[i].name || i + 1}: ${p}`;
  }
  return null;
}

// --- fake API rules: values that follow the declared type ---

export const slotOf = (slots: Slot[], name: string): Slot | undefined => slots.find((s) => s.name.trim() === name && s.type);

/** Text for a table cell. A typed value shows as typed ("4821" for digits, 4821 for number); an untyped one as before. */
export function fmtValue(slot: Slot | undefined, v: unknown): string {
  if (!slot) return fmt(v);
  if (slot.type === "boolean") return v === true ? "true" : v === false ? "false" : String(v);
  return typeof v === "string" ? v : String(v);
}

/** The value written for a cell: digits, text, dates and choices stay text (the engine reads "0042" as digits, not 42). */
export function parseValue(slot: Slot | undefined, text: string): unknown {
  if (!slot) return parse(text);
  if (slot.type === "boolean") return text === "true";
  if (slot.type === "number") return text.trim() !== "" && !Number.isNaN(Number(text)) ? Number(text) : text;
  return text;
}

/** Why a typed cell is refused, or null: the same tests as the engine's `value_fits`. */
export function valueProblem(slot: Slot | undefined, text: string): string | null {
  if (!slot || text === "") return null;
  if (slot.type === "digits") {
    if (!/^\d+$/.test(text)) return "숫자만 넣어 주세요";
    if (slot.length && text.length !== Number(slot.length)) return `${slot.length}자리로 넣어 주세요`;
  }
  if (slot.type === "number" && Number.isNaN(Number(text))) return "숫자를 넣어 주세요";
  if (slot.type === "choice" && !slot.choices.includes(text)) return "보기에 없는 값이에요";
  return null;
}
