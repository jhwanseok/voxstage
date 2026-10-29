/** 대화로 테스트: a panel docked on the right (floating over the page below 1280 px, so the scenario canvas keeps its room) that runs the validated draft on typed turns (backend `studio_backend/chat.py`).
 *  Each bot reply carries what happened in that turn: scenario and step, 속성 collected, API calls with the 넘긴 속성 and
 *  the result, re-asks. Terms follow DESIGN-NOTES (속성, 항목, 고정값). */
import { Keyboard, MessageSquare, RotateCcw, Send, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useBotActions } from "../actions";
import { ApiError, api, type Bot } from "../api";
import { Button, cn, Disclosure, Field, IconButton, Input, Notice, Segmented, StatusChip, Tag } from "../ui";

interface Started { id: string; draft_revision: number; shared_revision: number; stale: boolean; buttons: string[]; labels: Record<string, string> }
interface Call {
  tool: string; args: Record<string, unknown>; ok: boolean; data: Record<string, unknown> | null; error: string | null;
  step: { node: string; bind: Record<string, any>; args: Record<string, string> } | null;
}
export interface TurnOut {
  reply: string; actions: { kind: string; reason?: string }[];
  before: { flow: string | null; node: string | null }; after: { flow: string | null; node: string | null };
  attributes: Record<string, unknown>; changed: string[]; calls: Call[]; meta: Record<string, any>; trace: Record<string, any>;
  stale: boolean;
}
type Line = { who: "user"; text: string; kind: Kind } | { who: "bot"; turn: TurnOut };
type Kind = "text" | "digits" | "button";

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

/** Where a bound param came from, in the words of the binding form. */
function sourceText(src: any, labels: Record<string, string>): string {
  if (!src || typeof src !== "object") return "";
  if ("role" in src) return labels[`${src.role}.${src.field}`] ?? `${src.role}.${src.field}`;
  if ("call" in src) return `${src.call} 결과의 ${src.field}`;
  if ("const" in src) return "고정값";
  return "";
}

/** What happened in one turn, folded under the bot's reply. */
export function TurnDetails({ t, labels }: { t: TurnOut; labels: Record<string, string> }) {
  const attrs = Object.entries(t.attributes);
  const misses = Number(t.meta.ask_misses ?? 0);
  const where = t.after.flow ? `${t.after.flow} · ${t.after.node ?? "끝"}` : "진행 중인 시나리오 없음";
  return (
    <Disclosure title="이 턴에서 일어난 일" summary={<span className="font-mono text-[11px]">{where}</span>}>
      <dl className="space-y-3 text-[12px]">
        <div>
          <dt className="font-medium text-ink-2">시나리오와 단계</dt>
          <dd className="mt-0.5 font-mono text-ink">
            {t.before.flow !== t.after.flow || t.before.node !== t.after.node
              ? <>{t.before.flow ? `${t.before.flow} · ${t.before.node}` : "시작 전"} → {t.after.flow ? `${t.after.flow} · ${t.after.node}` : "끝"}</>
              : where}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink-2">수집한 속성</dt>
          <dd className="mt-0.5">
            {attrs.length === 0 ? <span className="text-muted">아직 없어요</span> : (
              <ul className="space-y-0.5">
                {attrs.map(([k, v]) => (
                  <li key={k} className={cn("flex flex-wrap items-baseline gap-x-1.5", t.changed.includes(k) && "font-semibold")}>
                    <span className="text-ink">{labels[k] ?? k}</span>
                    {labels[k] && <code className="text-[11px] text-muted">{k}</code>}
                    <span className="text-muted">=</span><code className="text-ink">{show(v)}</code>
                    {t.changed.includes(k) && <Tag tone="brand">이번 턴</Tag>}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        {t.calls.length > 0 && (
          <div>
            <dt className="font-medium text-ink-2">호출한 API</dt>
            <dd className="mt-0.5 space-y-2">
              {t.calls.map((c, i) => (
                <div key={i} className="rounded-md bg-sunken px-2.5 py-2">
                  <div className="flex items-center gap-1.5">
                    <code className="font-semibold text-ink">{c.tool}</code>
                    {c.step && <span className="text-muted">({c.step.node} 단계)</span>}
                    <span className="flex-1" />
                    <StatusChip tone={c.ok ? "ok" : "err"}>{c.ok ? "성공" : `실패: ${c.error}`}</StatusChip>
                  </div>
                  <div className="mt-1.5 text-muted">넘긴 속성</div>
                  <ul className="space-y-0.5">
                    {Object.entries(c.args).map(([p, v]) => {
                      const src = c.step?.bind[p];
                      return (
                        <li key={p}><code>{p}</code> = <code className="text-ink">{show(v)}</code>
                          <span className="text-muted"> {src ? `← ${sourceText(src, labels)}` : c.step?.args[p] ? `← ${c.step.args[p]} (예전 방식)` : ""}</span></li>
                      );
                    })}
                  </ul>
                  {c.ok && c.data && Object.keys(c.data).length > 0 && (
                    <><div className="mt-1.5 text-muted">돌려받은 항목</div>
                      <ul>{Object.entries(c.data).map(([k, v]) => <li key={k}><code>{k}</code> = <code className="text-ink">{show(v)}</code></li>)}</ul></>
                  )}
                </div>
              ))}
            </dd>
          </div>
        )}
        <div className="flex flex-wrap gap-1.5">
          {misses > 0 && <Tag tone="warn">재질문 {misses}번째</Tag>}
          {t.meta.verified && <Tag tone="ok">본인 확인됨</Tag>}
          {(t.meta.parked ?? []).length > 0 && <Tag tone="idle">잠시 미룬 시나리오 {(t.meta.parked as unknown[]).length}개</Tag>}
        </div>
        <Disclosure title="개발 정보" summary="엔진 기록">
          <pre className="max-h-48 overflow-auto rounded-md bg-sunken p-2 text-[11px] text-ink-2">{JSON.stringify(t.trace, null, 2)}</pre>
        </Disclosure>
      </dl>
    </Disclosure>
  );
}

export default function ChatTest({ bot, onClose }: { bot: Bot; onClose: () => void }) {
  const { validate, validating } = useBotActions();
  const [session, setSession] = useState<Started | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"text" | "digits">("text");
  const [now, setNow] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [ended, setEnded] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const ready = bot.validated && bot.valid;

  const start = async () => {
    if (session) void api.del(`/bots/${bot.slug}/chat/${session.id}`).catch(() => undefined);
    setLines([]); setError(""); setStale(false); setEnded(false); setSession(null);
    if (!ready) return;
    try {
      const setup = now ? { now: now.length === 16 ? `${now}:00` : now } : {};
      setSession(await api.post<Started>(`/bots/${bot.slug}/chat`, { setup }));
      window.setTimeout(() => input.current?.focus(), 0);
    } catch (e) { setError(e instanceof ApiError && e.status === 409 ? "검증을 통과한 초안만 대화해 볼 수 있어요." : (e as Error).message); }
  };
  // a new session whenever the bot or its validity changes; the old one ends with the panel
  useEffect(() => { void start(); }, [bot.slug, ready]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (session) void api.del(`/bots/${bot.slug}/chat/${session.id}`).catch(() => undefined); }, [session, bot.slug]);
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: "end" }); }, [lines]);
  useEffect(() => { if (session && (bot.draft_revision !== session.draft_revision || bot.shared_revision !== session.shared_revision)) setStale(true); },
    [bot.draft_revision, bot.shared_revision, session]);

  const send = async (k: Kind, raw: string) => {
    const t = raw.trim();
    if (!session || !t || busy) return;
    setBusy(true); setError("");
    setLines((ls) => [...ls, { who: "user", text: t, kind: k }]);
    if (k !== "button") setText("");
    try {
      const out = await api.post<TurnOut>(`/bots/${bot.slug}/chat/${session.id}/turns`, { kind: k, text: t });
      setLines((ls) => [...ls, { who: "bot", turn: out }]);
      if (out.stale) setStale(true);
      if (out.actions.some((a) => a.kind === "handoff" || a.kind === "end_call")) setEnded(true);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "대화가 끝났어요. 처음부터 다시 시작해 주세요." : (e as Error).message);
    } finally { setBusy(false); input.current?.focus(); }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); void send(kind, text); };

  return (
    <aside aria-label="대화로 테스트" className="sticky top-14 flex h-[calc(100vh-3.5rem)] w-[400px] shrink-0 flex-col border-l border-line bg-surface max-xl:fixed max-xl:right-0 max-xl:z-30 max-xl:w-[380px] max-xl:max-w-full max-xl:shadow-2xl">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3">
        <MessageSquare size={16} className="text-brand-700" aria-hidden />
        <h2 className="text-sm font-semibold text-ink">대화로 테스트</h2>
        {session && <span className="num text-xs text-muted">초안 {session.draft_revision}</span>}
        <span className="flex-1" />
        <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} disabled={!ready} onClick={() => void start()}>처음부터 다시</Button>
        <IconButton label="대화로 테스트 닫기" onClick={onClose}><X size={16} /></IconButton>
      </div>

      {!ready ? (
        <div className="space-y-3 p-4">
          <Notice tone={bot.validated ? "err" : "warn"} title={bot.validated ? "고칠 곳이 있어 대화해 볼 수 없어요" : "검증한 뒤에 대화해 볼 수 있어요"}>
            {bot.validated ? "검증에서 나온 문제를 고치고 다시 검증해 주세요." : "지금 초안이 엔진에서 읽히는지 먼저 확인해야 해요."}
          </Notice>
          <Button variant="primary" icon={<ShieldCheck size={15} />} loading={validating} onClick={() => void validate()}>검증하기</Button>
        </div>
      ) : (
        <>
          <div className="border-b border-line px-4 py-2">
            <Disclosure title="시작 조건" summary={now ? `기준 시각 ${now.replace("T", " ")}` : "기준 시각: 지금"}>
              <div className="space-y-2">
                <Field label="기준 시각" optional hint="'다음 달 십오일' 같은 날짜를 이 시각으로 계산해요. 바꾸면 처음부터 다시 시작해요.">
                  <Input type="datetime-local" value={now} onChange={(e) => setNow(e.target.value)} />
                </Field>
                <Button size="sm" onClick={() => void start()}>이 조건으로 다시 시작</Button>
              </div>
            </Disclosure>
          </div>
          {stale && (
            <div className="px-4 pt-3">
              <Notice tone="warn" title="초안이 바뀌었어요" action={<Button size="sm" onClick={() => void start()}>다시 시작</Button>}>
                이 대화는 바뀌기 전 초안으로 돌고 있어요. 바뀐 내용은 다시 검증한 뒤 새 대화에서 볼 수 있어요.
              </Notice>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" aria-live="polite">
            {lines.length === 0 && (
              <p className="py-6 text-center text-[13px] text-muted">고객이 되어 말을 걸어 보세요.<br />예: 시나리오의 시작하는 말이나 자주 묻는 질문</p>
            )}
            <ol className="space-y-3">
              {lines.map((l, i) => l.who === "user" ? (
                <li key={i} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-500 px-3 py-2 text-[13px] text-on-brand">
                    {l.kind === "digits" && <Keyboard size={12} className="mr-1 inline" aria-label="키패드" />}
                    {l.kind === "button" && <span className="mr-1 text-[11px] opacity-80">버튼</span>}
                    {l.text}
                  </div>
                </li>
              ) : (
                <li key={i} className="space-y-1.5">
                  <div className="max-w-[90%] rounded-2xl rounded-bl-md bg-sunken px-3 py-2 text-[13px] text-ink">{l.turn.reply || <span className="italic text-muted">말없이 기다려요</span>}</div>
                  {l.turn.actions.map((a, k) => (
                    <div key={k} className="text-xs font-medium text-warn-fg">{a.kind === "handoff" ? `상담사에게 연결해요 (${a.reason})` : a.kind === "end_call" ? "통화를 끝내요" : a.kind}</div>
                  ))}
                  <TurnDetails t={l.turn} labels={session?.labels ?? {}} />
                </li>
              ))}
            </ol>
            <div ref={bottom} />
          </div>
          {error && <div className="px-4 pb-2"><Notice tone="err" title={error} /></div>}
          {ended && <p className="px-4 pb-2 text-xs text-muted">통화가 끝난 상태예요. 계속 말하면 새 문의로 받아요.</p>}
          {(session?.buttons.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-1.5 px-4 pb-2" aria-label="시나리오 버튼">
              {session!.buttons.map((b) => <Button key={b} size="sm" disabled={busy} onClick={() => void send("button", b)}>{b}</Button>)}
            </div>
          )}
          <form onSubmit={submit} className="flex items-center gap-2 border-t border-line px-4 py-3">
            <Segmented label="입력 방식" value={kind} onChange={(k) => { setKind(k); input.current?.focus(); }}
              options={[{ value: "text", label: "말" }, { value: "digits", label: "키패드" }]} />
            <Input ref={input} aria-label={kind === "digits" ? "누를 숫자" : "고객이 하는 말"} value={text} disabled={!session}
              inputMode={kind === "digits" ? "numeric" : undefined} placeholder={kind === "digits" ? "예: 5580" : "고객이 하는 말"}
              onChange={(e) => setText(kind === "digits" ? e.target.value.replace(/[^0-9*#]/g, "") : e.target.value)} className="flex-1" />
            <IconButton label="보내기" type="submit" disabled={!session || busy || !text.trim()}><Send size={16} /></IconButton>
          </form>
        </>
      )}
    </aside>
  );
}
