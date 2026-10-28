import { Download, FileText, History as HistoryIcon } from "lucide-react";
import { useState } from "react";
import { api, type Bot, type Publication } from "../api";
import { when } from "../copy";
import { useFetch } from "../hooks";
import { cn, EmptyState, ErrorState, LoadingBlock, Notice, PageHeader } from "../ui";

interface PubDetail extends Publication { files: { path: string; size: number }[] }

export default function History({ bot }: { bot: Bot }) {
  const { data: pubs, error, loading, reload } = useFetch<Publication[]>(`/bots/${bot.slug}/publications`, [bot.last_published_number]);
  const [open, setOpen] = useState<PubDetail | null>(null);
  const [file, setFile] = useState<{ path: string; text: string } | null>(null);
  const [fail, setFail] = useState("");
  const show = async (n: number) => {
    setFile(null); setFail("");
    try { setOpen(await api.get<PubDetail>(`/bots/${bot.slug}/publications/${n}`)); } catch (e) { setFail((e as Error).message); }
  };
  const view = async (path: string) => {
    const res = await fetch(`/api/v1/bots/${bot.slug}/publications/${open!.number}/files/${path}`);
    setFile({ path, text: await res.text() });
  };
  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <PageHeader title="게시 이력" description="게시한 버전은 바뀌지 않고 남아요. 가장 최근 버전이 엔진이 읽는 폴더에 나가 있어요." />
      {error && <ErrorState error={error} onRetry={reload} what="게시 이력" />}
      {loading && <LoadingBlock rows={4} />}
      {pubs && pubs.length === 0 && (
        <EmptyState icon={<HistoryIcon size={20} />} title="아직 게시한 버전이 없어요">위의 검증하기와 게시하기로 첫 버전을 내보내 보세요.</EmptyState>
      )}
      {pubs && pubs.length > 0 && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
          <ol className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
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
                  <div className="mt-0.5 truncate text-[13px] text-ink-2">{p.note || <span className="text-muted">메모 없음</span>}</div>
                </button>
              </li>
            ))}
          </ol>
          <div className="min-w-0 rounded-xl border border-line bg-surface p-5">
            {fail && <Notice tone="err" title="버전을 불러오지 못했어요">{fail}</Notice>}
            {!open && !fail && <p className="text-sm text-muted">왼쪽에서 버전을 골라 내보낸 파일을 볼 수 있어요.</p>}
            {open && (
              <>
                <div className="mb-3 flex items-center gap-3">
                  <h2 className="flex-1 text-[15px] font-semibold text-ink">{open.number}번째 버전의 파일 {open.files.length}개</h2>
                  <a className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline" href={`/api/v1/bots/${bot.slug}/publications/${open.number}/export.zip`}><Download size={15} aria-hidden />zip 내려받기</a>
                </div>
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
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
