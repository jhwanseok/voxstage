import { BookOpenText, Download, GitBranch, PlugZap, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type BotDetail, type Domain } from "../api";
import { botName, botStatus, domainName, langName } from "../copy";
import { useFetch, useShell } from "../hooks";
import { paths } from "../paths";
import { Button, EmptyState, ErrorState, LoadingBlock, Notice, PageHeader, StatusChip, useToast } from "../ui";

function BotCard({ slug }: { slug: string }) {
  const { version } = useShell();
  const { data: b } = useFetch<BotDetail>(`/bots/${slug}`, [version]);
  if (!b) return <div className="h-[148px] rounded-xl border border-line bg-surface p-5"><div className="skeleton h-5 w-1/2" /></div>;
  const st = botStatus(b);
  return (
    <Link to={paths.bot(b.slug)} className="group block rounded-xl border border-line bg-surface p-5 transition-colors hover:border-brand-500">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-lg font-semibold text-ink group-hover:text-brand-700">{botName(b)}</div>
          <div className="mt-0.5 text-xs text-muted">{langName(b.lang)}</div>
        </div>
        <StatusChip tone={st.tone}>{st.text}</StatusChip>
      </div>
      <dl className="mt-5 flex gap-6 text-sm text-ink-2">
        <div className="flex items-center gap-1.5"><BookOpenText size={15} className="text-muted" aria-hidden /><dt className="sr-only">질문</dt><dd>질문 <b className="num text-ink">{b.counts.faq}</b></dd></div>
        <div className="flex items-center gap-1.5"><GitBranch size={15} className="text-muted" aria-hidden /><dt className="sr-only">시나리오</dt><dd>시나리오 <b className="num text-ink">{b.counts.flows}</b></dd></div>
        <div className="flex items-center gap-1.5"><PlugZap size={15} className="text-muted" aria-hidden /><dt className="sr-only">API</dt><dd>API <b className="num text-ink">{b.counts.tools}</b></dd></div>
      </dl>
      <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
        {b.last_published_number ? `${b.last_published_number}번째 버전이 엔진에 나가 있어요` : "아직 게시한 버전이 없어요"}
      </div>
    </Link>
  );
}

export default function Home() {
  const { refresh, version } = useShell();
  const toast = useToast();
  const { data: domains, error, loading, reload } = useFetch<Domain[]>("/domains", [version]);
  const { data: importable } = useFetch<string[]>("/domains/importable", [version]);
  const [busy, setBusy] = useState("");

  const run = async (name: string, replace: boolean) => {
    if (replace && !window.confirm(`${domainName(name)} 초안을 저장소의 domains/${name} 파일로 바꿀까요? 게시 이력은 남아요.`)) return;
    setBusy(name);
    try {
      const s = await api.post<{ bots: { slug: string }[] }>("/domains/import", { domain: name, replace });
      toast(`${domainName(name)} 상담봇 ${s.bots.length}개를 가져왔어요`); refresh(); reload();
    } catch (e) {
      toast(e instanceof ApiError ? String(e.message) : (e as Error).message, "err");
    } finally { setBusy(""); }
  };

  const bots = (domains ?? []).flatMap((d) => d.bots);
  const waiting = bots.filter((b) => b.has_unpublished_changes).length;
  const present = new Set((domains ?? []).map((d) => d.slug));
  const notImported = (importable ?? []).filter((n) => !present.has(n));

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <PageHeader title="어떤 상담봇을 다듬어 볼까요?"
        description="상담봇은 업종 하나와 언어 하나로 이루어져요. 질문과 시나리오를 고친 뒤 검증하고 게시하면 엔진이 새 버전을 읽어요." />
      {error && <ErrorState error={error} onRetry={reload} what="상담봇 목록" />}
      {loading && <LoadingBlock rows={3} />}
      {domains && bots.length === 0 && (
        <EmptyState icon={<Download size={20} />} title="아직 상담봇이 없어요"
          action={notImported[0] && <Button variant="primary" loading={busy === notImported[0]} onClick={() => run(notImported[0], false)}>{domainName(notImported[0])} 가져오기</Button>}>
          저장소의 domains 폴더에 있는 업종을 가져오면 언어마다 상담봇이 하나씩 생겨요.
        </EmptyState>
      )}
      {bots.length > 0 && (
        <p className="mb-5 text-sm text-ink-2">
          상담봇 <b className="num">{bots.length}</b>개 중 <b className="num">{waiting}</b>개에 아직 게시하지 않은 변경이 있어요.
        </p>
      )}
      {(domains ?? []).filter((d) => d.bots.length).map((d) => (
        <section key={d.slug} className="mb-8" aria-labelledby={`dom-${d.slug}`}>
          <div className="mb-3 flex items-center gap-3">
            <h2 id={`dom-${d.slug}`} className="text-[15px] font-semibold text-ink">{domainName(d.slug)}</h2>
            <span className="h-px flex-1 bg-line" />
            <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} loading={busy === d.slug} onClick={() => run(d.slug, true)}>저장소 파일로 다시 가져오기</Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">{d.bots.map((b) => <BotCard key={b.slug} slug={b.slug} />)}</div>
        </section>
      ))}
      {bots.length > 0 && notImported.length > 0 && (
        <Notice tone="brand" title="가져올 수 있는 업종이 더 있어요"
          action={<div className="flex gap-2">{notImported.map((n) => <Button key={n} size="sm" loading={busy === n} onClick={() => run(n, false)}>{domainName(n)} 가져오기</Button>)}</div>} />
      )}
    </main>
  );
}
