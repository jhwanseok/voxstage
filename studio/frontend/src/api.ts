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
  slug: string; domain: string; lang: string; title: string;
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
}
export interface Tool { name: string; position: number; body: Record<string, any>; revision: number }
export interface FlowSummary {
  id: string; start: string; node_count: number; buttons: string[]; role: string | null; triggers: any; items: Item[];
}
export interface GraphNode { id: string; type: string; data: Record<string, any> }
export interface GraphEdge { id: string; from: string; to: string; label: string; handle: string }
export interface FlowDetail {
  flow: { id: string; header: Record<string, any>; start: string; nodes: Record<string, any>; node_order: string[]; revision: number };
  layout: { viewport: any; direction: string; nodes: Record<string, { x: number; y: number; collapsed?: boolean }> };
  graph: { start: string; nodes: GraphNode[]; edges: GraphEdge[] };
  items: Item[];
}
export interface Publication {
  number: number; note: string; kind: string; published_by: string | null; published_at: string;
  content_hash: string; file_count?: number;
}
