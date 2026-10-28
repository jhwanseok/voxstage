import { GitBranch, Plus, UserCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api, type Bot, type FlowSummary } from "../api";
import { useFetch, useShell } from "../hooks";
import { paths } from "../paths";
import { Button, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, StatusChip, Tag } from "../ui";

function triggerWords(t: any): { inc: string[]; exc: string[] } {
  if (!t) return { inc: [], exc: [] };
  const inc = [...(t.any_of ?? []), ...(t.all_of ?? []).map((g: any) => (Array.isArray(g) ? g.join("/") : String(g)))];
  return { inc, exc: t.none_of ?? [] };
}

function NewFlow({ bot, ids, onClose }: { bot: Bot; ids: string[]; onClose: () => void }) {
  const nav = useNavigate();
  const { refresh } = useShell();
  const [id, setId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const bad = id && !/^[a-z][a-z0-9_]*$/.test(id) ? "영문 소문자로 시작하고 소문자, 숫자, 밑줄만 써 주세요" : ids.includes(id) ? "이미 있는 이름이에요" : null;
  const create = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/bots/${bot.slug}/flows`, { id }); refresh(); nav(paths.flow(bot.slug, id)); }
    catch (e) { setErr(e instanceof ApiError ? String(e.message) : (e as Error).message); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open onClose={onClose} title="새 시나리오"
      footer={<><Button onClick={onClose}>취소</Button><Button variant="primary" loading={busy} disabled={!id || !!bad} onClick={create}>만들고 편집하기</Button></>}>
      <p className="mb-4 text-sm text-ink-2">끝내기 단계 하나로 시작해요. 편집 화면에서 시작하는 말과 단계를 채워 보세요.</p>
      <Field label="시나리오 이름" hint="파일 이름이 돼요. 예: card_reissue" error={bad ?? (err || null)}>
        <Input data-autofocus className="font-mono" value={id} onChange={(e) => setId(e.target.value.trim())}
          onKeyDown={(e) => { if (e.key === "Enter" && id && !bad) void create(); }} />
      </Field>
    </Dialog>
  );
}

export default function Flows({ bot }: { bot: Bot }) {
  const { data: flows, error, loading, reload } = useFetch<FlowSummary[]>(`/bots/${bot.slug}/flows`, [bot.draft_revision, bot.validated]);
  const [creating, setCreating] = useState(false);
  const list = flows ?? [];
  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="시나리오" count={flows ? list.length : undefined}
        description="고객의 말로 시작해 여러 단계를 거쳐 끝나는 대화예요. 눌러서 단계를 고칠 수 있어요."
        actions={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>새 시나리오</Button>} />
      {error && <ErrorState error={error} onRetry={reload} what="시나리오 목록" />}
      {loading && <LoadingBlock rows={5} label="시나리오를 불러오는 중" />}
      {flows && list.length === 0 && (
        <EmptyState icon={<GitBranch size={20} />} title="아직 시나리오가 없어요"
          action={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>첫 시나리오 만들기</Button>}>
          이체, 카드 분실 신고처럼 여러 단계를 거치는 대화를 만들어 보세요.
        </EmptyState>
      )}
      {list.length > 0 && (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {list.map((f) => {
            const { inc, exc } = triggerWords(f.triggers);
            const errors = f.items.filter((i) => i.severity === "error").length;
            return (
              <li key={f.id}>
                <Link to={paths.flow(bot.slug, f.id)} className="flex items-center gap-4 px-5 py-4 hover:bg-sunken/60">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink">{f.id}</span>
                      {f.role === "verification" && <StatusChip tone="brand" icon={false}><UserCheck size={12} aria-hidden />본인 확인</StatusChip>}
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1">
                      {f.role === "verification" ? <span className="text-[13px] text-muted">다른 시나리오가 부를 때 시작해요</span> : (
                        <>
                          {inc.slice(0, 6).map((w) => <Tag key={w} tone="ok">{w}</Tag>)}
                          {exc.length > 0 && <span className="ml-1 text-xs text-muted">제외 {exc.slice(0, 3).join(", ")}{exc.length > 3 ? ` 외 ${exc.length - 3}` : ""}</span>}
                          {f.buttons.length > 0 && <span className="ml-1 text-xs text-muted">버튼 {f.buttons.join(", ")}</span>}
                          {!inc.length && !f.buttons.length && <span className="text-[13px] text-warn-fg">시작하는 말이 아직 없어요</span>}
                        </>
                      )}
                    </div>
                  </div>
                  <span className="num whitespace-nowrap text-xs text-muted">단계 {f.node_count}개</span>
                  {errors > 0 ? <StatusChip tone="err">고칠 곳 {errors}개</StatusChip> : bot.validated ? <StatusChip tone="ok">문제 없음</StatusChip> : null}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {creating && <NewFlow bot={bot} ids={list.map((f) => f.id)} onClose={() => setCreating(false)} />}
    </main>
  );
}
