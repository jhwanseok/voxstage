/** Text <-> JSON value for table cells: `4821` is a number, `"4821"` is a string, `abc` is a string. */
export function fmt(v: unknown): string {
  if (typeof v === "string") {
    try { JSON.parse(v); return JSON.stringify(v); } catch { return v; }
  }
  return JSON.stringify(v);
}

export function parse(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
}

export function lines(s: string): string[] {
  return s.split("\n").map((x) => x.trim()).filter(Boolean);
}

export function words(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}
