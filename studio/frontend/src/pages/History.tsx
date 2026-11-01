import { Download, FileText, History as HistoryIcon, Undo2 } from "lucide-react";
import { useState } from "react";
import { ApiError, api, type Bot, type Publication, type Report } from "../api";
import { when } from "../copy";
import { useFetch, useShell } from "../hooks";
import type { Comparison } from "../lib/changes";
import { Button, cn, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock, Notice, PageHeader, Select, useToast } from "../ui";
import { ChangeSummary } from "./ChangeSummary";

interface PubDetail extends Publication { files: { path: string; size: number }[] }

/** Words for what a comparison shows, by what it is compared with. */
export function compareTitle(n: number, against: string): string {
  if (against === "previous") return `${n}번째 버전이 이전 버전과 다른 점`;
  if (against === "draft") return `지금 초안을 ${n}번째 버전으로 되돌리면 바뀌는 것`;
  return `${against}번째 버전에서 ${n}번째 버전으로 가면 바뀌는 것`;
}

function Compare({ bot, n, pubs }: { bot: Bot; n: number; pubs: Publication[] }) {
  const [against, setAgainst] = useState("previous");
  const { data, error, loading } = useFetch<Comparison>(`/bots/${bot.slug}/publications/${n}/diff?against=${against}`, [bot.draft_revision]);
  return (
    <section className="mb-6" aria-label="비교">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="flex-1 text-[15px] font-semibold text-ink">{compareTitle(n, against)}</h3>
        <label className="flex items-center gap-2 text-[13px] text-ink-2">비교 대상
          <Select value={against} onChange={(e) => setAgainst(e.target.value)} className="w-auto">
            <option value="previous">이전 버전</option>
            {pubs.filter((p) => p.number !== n).map((p) => <option key={p.number} value={String(p.number)}>{p.number}번째 버전</option>)}
            <option value="draft">지금 초안</option>
          </Select>
        </label>
      </div>
      {error && <ErrorState error={error} what="비교" />}
      {loading && <LoadingBlock rows={2} />}
      {data && (
        <>
          {data.base.kind === "none" && <div className="mb-3"><Notice tone="idle" title="이보다 앞선 버전이 없어서 모든 파일이 새것으로 보여요">오래된 버전은 최근 5개만 보관해요.</Notice></div>}
          <ChangeSummary data={data} />
        </>
      )}
    </section>
  );
}

/** Roll back: a new version from the old one's own files, and the draft replaced. Shared files stay as they are. */
export function RollbackDialog({ bot, pub, onClose, onDone }: { bot: Bot; pub: Publication; onClose: () => void; onDone: (p: Publication) => void }) {
  const { data: preview } = useFetch<Comparison>(`/bots/${bot.slug}/publications/${pub.number}/diff?against=draft`);
  const [note, setNote] = useState(`${pub.number}번째 버전으로 되돌림`);
  const [busy, setBusy] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [message, setMessage] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const go = async (discardDraft: boolean) => {
    setBusy(true); setMessage(""); setReport(null);
    try {
      onDone(await api.post<Publication>(`/bots/${bot.slug}/publications/${pub.number}/rollback`, { note, discard_draft: discardDraft }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.body?.code === "unpublished_changes") setDiscard(true);
      else if (e instanceof ApiError && e.status === 409) setMessage("지금 가장 최근 버전이 이미 이 내용이에요. 되돌릴 것이 없어요.");
      else if (e instanceof ApiError && e.status === 422 && e.body?.report) {
        setReport(e.body.report);
        setMessage("지금의 공통 파일(API 연결, 속성 형식)과 맞지 않아서 되돌리지 않았어요. 아래가 막은 이유예요.");
      } else setMessage((e as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onClose={onClose} title={`${pub.number}번째 버전으로 되돌리기`}
      footer={<><Button onClick={onClose}>취소</Button>
        <Button variant={discard ? "danger" : "primary"} loading={busy} icon={<Undo2 size={15} />} onClick={() => go(discard)}>
          {discard ? "초안을 버리고 되돌리기" : "되돌리기"}</Button></>}>
      <p className="mb-3 text-sm text-ink-2">이 봇의 파일을 {pub.number}번째 버전과 똑같이 만들고, 그 내용을 새 버전으로 게시해요. 이력은 지워지지 않아요. 지금 초안은 이 내용으로 바뀌어요.</p>
      <Notice tone="brand" title="업종 공통 파일은 되돌리지 않아요">API 연결, 속성 형식, 목록은 다른 언어 봇과 함께 쓰는 파일이라 지금 것을 그대로 써요.</Notice>
      {preview && !preview.summary.empty && <div className="mt-4"><h3 className="mb-2 text-sm font-semibold text-ink">초안에서 바뀌는 것</h3><div className="max-h-52 overflow-y-auto pr-1"><ChangeSummary data={preview} /></div></div>}
      {discard && <div className="mt-4"><Notice tone="warn" title="아직 게시하지 않은 초안의 변경이 있어요">되돌리면 이 변경은 사라져요. 버려도 되면 아래 버튼으로 이어서 되돌리세요.</Notice></div>}
      <div className="mt-4"><Field label="메모" optional hint="게시 이력에 남아요."><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field></div>
      {message && <div className="mt-4"><Notice tone="err" title={message} /></div>}
      {report && (
        <ul className="mt-3 space-y-1.5 text-[13px]">
          {report.items.filter((i) => i.severity === "error").map((i, k) => (
            <li key={k} className="rounded-lg bg-sunken px-3 py-2"><span className="font-medium">{i.flow_id ? `시나리오 ${i.flow_id}` : i.file}</span><br /><span className="text-ink-2">{i.message}</span></li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

export default function History({ bot }: { bot: Bot }) {
  const { data: pubs, error, loading, reload } = useFetch<Publication[]>(`/bots/${bot.slug}/publications`, [bot.last_published_number]);
  const { refresh } = useShell();
  const toast = useToast();
  const [open, setOpen] = useState<PubDetail | null>(null);
  const [file, setFile] = useState<{ path: string; text: string } | null>(null);
  const [fail, setFail] = useState("");
  const [rolling, setRolling] = useState(false);
  const show = async (n: number) => {
    setFile(null); setFail("");
    try { setOpen(await api.get<PubDetail>(`/bots/${bot.slug}/publications/${n}`)); } catch (e) { setFail((e as Error).message); }
  };
  const view = async (path: string) => {
    const res = await fetch(`/api/v1/bots/${bot.slug}/publications/${open!.number}/files/${path}`);
    setFile({ path, text: await res.text() });
  };
  const rolled = (p: Publication) => {
    setRolling(false); setOpen(null); refresh(); reload(); toast(`${p.restored_from_number}번째 버전으로 되돌렸어요 (${p.number}번째 버전)`);
  };
  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <PageHeader title="게시 이력" description="게시한 버전은 바뀌지 않고 남아요. 최근 5개만 보관하고, 가장 최근 버전이 엔진이 읽는 폴더에 나가 있어요." />
      {error && <ErrorState error={error} onRetry={reload} what="게시 이력" />}
      {loading && <LoadingBlock rows={4} />}
      {pubs && pubs.length === 0 && (
        <EmptyState icon={<HistoryIcon size={20} />} title="아직 게시한 버전이 없어요">위의 검증하기와 게시하기로 첫 버전을 내보내 보세요.</EmptyState>
      )}
      {pubs && pubs.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ol className="divide-y divide-line self-start overflow-hidden rounded-xl border border-line bg-surface">
            {pubs.map((p, i) => (
              <li key={p.number}>
                <button type="button" onClick={() => show(p.number)} aria-current={open?.number === p.number || undefined}
                  className={cn("w-full px-4 py-3 text-left hover:bg-sunken/60", open?.number === p.number && "bg-brand-50")}>
                  <div className="flex items-baseline gap-2">
                    <span className="num font-semibold text-ink">{p.number}번째 버전</span>
                    {i === 0 && <span className="text-xs font-medium text-ok-fg">엔진에 나가 있음</span>}
                    <span className="flex-1" />
                    <span className="text-xs text-muted">{when(p.published_at)}</span>
                  </div>
                  {p.kind === "rollback" && <div className="mt-0.5 text-xs font-medium text-brand-700">{p.restored_from_number}번째 버전으로 되돌림</div>}
                  {p.published_by_name && <div className="mt-0.5 text-xs text-muted">{p.published_by_name}</div>}
                  <div className="mt-0.5 truncate text-[13px] text-ink-2">{p.note || <span className="text-muted">메모 없음</span>}</div>
                </button>
              </li>
            ))}
          </ol>
          <div className="min-w-0 rounded-xl border border-line bg-surface p-5">
            {fail && <Notice tone="err" title="버전을 불러오지 못했어요">{fail}</Notice>}
            {!open && !fail && <p className="text-sm text-muted">왼쪽에서 버전을 골라 이전 버전과 다른 점과 내보낸 파일을 볼 수 있어요.</p>}
            {open && (
              <>
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <h2 className="flex-1 text-[17px] font-bold text-ink">{open.number}번째 버전</h2>
                  {pubs[0].number !== open.number && <Button icon={<Undo2 size={15} />} onClick={() => setRolling(true)}>이 버전으로 되돌리기</Button>}
                  <a className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline" href={`/api/v1/bots/${bot.slug}/publications/${open.number}/export.zip`}><Download size={15} aria-hidden />zip 내려받기</a>
                </div>
                <Compare key={open.number} bot={bot} n={open.number} pubs={pubs} />
                <h3 className="mb-2 text-[15px] font-semibold text-ink">내보낸 파일 {open.files.length}개</h3>
                <ul className="max-h-64 overflow-auto rounded-lg border border-line">
                  {open.files.map((f) => (
                    <li key={f.path}>
                      <button type="button" onClick={() => view(f.path)} className={cn("flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-sunken", file?.path === f.path && "bg-brand-50")}>
                        <FileText size={14} className="text-muted" aria-hidden /><span className="flex-1 truncate font-mono">{f.path}</span><span className="num text-xs text-muted">{f.size.toLocaleString()} B</span>
                      </button>
                    </li>
                  ))}
                </ul>
                {file && <pre className="mt-4 max-h-[50vh] overflow-auto rounded-lg bg-sunken p-4 text-xs leading-relaxed text-ink-2"><b className="mb-2 block font-mono text-ink">{file.path}</b>{file.text}</pre>}
                {rolling && <RollbackDialog bot={bot} pub={open} onClose={() => setRolling(false)} onDone={rolled} />}
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
