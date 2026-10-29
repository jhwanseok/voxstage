export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(typeof body === "string" ? body : body?.detail?.message ?? body?.detail ?? body?.message ?? `HTTP ${status}`);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: any = text;
  try { data = JSON.parse(text); } catch { /* plain text */ }
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const api = {
  get: <T,>(p: string) => call<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  put: <T,>(p: string, b: unknown) => call<T>("PUT", p, b),
  del: (p: string) => call<void>("DELETE", p),
};

export interface Bot {
  slug: string; domain: string; domain_title: string; lang: string; title: string;
  /** the bot this one was copied from, and how many of its items still hold that bot's language */
  copied_from: string | null; to_translate: number;
  draft_revision: number; shared_revision: number; last_published_number: number;
  has_unpublished_changes: boolean; validated: boolean; valid: boolean;
}
export interface Domain { slug: string; title: string; bots: Bot[] }
export interface Item {
  severity: "error" | "warning"; source: string; code: string; file: string; lang: string | null;
  flow_id: string | null; node_id: string | null; field: string | null; message: string;
}
export interface Report { ok: boolean; draft_revision: number; shared_revision: number; items: Item[] }
export interface Pattern { all_of?: any[]; any_of?: string[]; none_of?: string[]; priority?: number; regex?: string[]; note?: string }
export interface Faq {
  id: string; position: number; question: string; answer: string; paraphrases: string[] | null;
  asr_variants: string[] | null; pattern: Pattern | null; revision: number;
  /** against the newest publication; null when the bot was never published */
  published?: "same" | "changed" | "new" | null;
  /** copied from another language and not saved since */
  to_translate?: boolean;
}
export interface Tool { name: string; position: number; body: Record<string, any>; revision: number }
export interface FlowSummary {
  id: string; start: string; node_count: number; buttons: string[]; role: string | null; triggers: any; items: Item[]; to_translate?: boolean;
}
export interface GraphNode { id: string; type: string; data: Record<string, any> }
export interface GraphEdge { id: string; from: string; to: string; label: string; handle: string }
export interface FlowDetail {
  flow: { id: string; header: Record<string, any>; start: string; nodes: Record<string, any>; node_order: string[]; revision: number };
  layout: { viewport: any; direction: string; nodes: Record<string, { x: number; y: number; collapsed?: boolean }> };
  graph: { start: string; nodes: GraphNode[]; edges: GraphEdge[] };
  items: Item[];
}
export interface ToTranslate { faq: string[]; flows: string[]; notices: string[] }
export interface BotDetail extends Bot { counts: { faq: number; flows: number; tools: number }; translate: ToTranslate }

export type OnExceed = "handoff" | "end_call";
export interface EngineSettings {
  fallback: { max_misses: number; on_exceed: OnExceed };
  ask: { max_reprompts: number; on_exceed: OnExceed };
  switch: { max_parked: number };
  correction: { max_corrections: number; on_exceed: OnExceed };
  verification: { max_attempts: number; on_exceed: OnExceed };
  tools: { max_failures: number; timeout_ms: number; on_exceed: OnExceed };
}
export interface BotSettings {
  slug: string; title: string; lang: string; domain: string; domain_title: string; revision: number; has_config_file: boolean;
  engine: EngineSettings;
  studio_only: { handoff_number: string | null; policy: Record<string, string> };
  policy_refs: { key: string; flows: string[] }[];
}

export interface Publication {
  number: number; note: string; kind: string; published_by: string | null; published_at: string;
  content_hash: string; file_count?: number;
}
