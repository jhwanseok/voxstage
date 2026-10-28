import { ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { useBotActions } from "../actions";
import { type Bot, type Report } from "../api";
import { useFetch } from "../hooks";
import { paths } from "../paths";
import { Button, EmptyState, ErrorState, LoadingBlock, Notice, PageHeader, StatusChip } from "../ui";

/** Where a problem lives, as a link to the screen that fixes it. */
function Where({ bot, file, flow, node }: { bot: Bot; file: string; flow: string | null; node: string | null }) {
  const cls = "font-medium text-brand-700 hover:underline";
  if (flow) return <Link className={cls} to={paths.flow(bot.slug, flow)}>시나리오 {flow}{node ? `, 단계 ${node}` : ""}</Link>;
  if (/faq/.test(file)) return <Link className={cls} to={paths.bot(bot.slug, "faq")}>자주 묻는 질문</Link>;
  if (/tools/.test(file)) return <Link className={cls} to={paths.bot(bot.slug, "tools")}>API 연결</Link>;
  if (/config/.test(file)) return <Link className={cls} to={paths.bot(bot.slug)}>기본 설정</Link>;
  return <span className="font-mono text-xs text-ink-2">{file}</span>;
}

export default function Validation({ bot }: { bot: Bot }) {
  const { validate, validating, openPublish } = useBotActions();
  const { data: report, error, loading, reload } = useFetch<Report | null>(`/bots/${bot.slug}/validation`, [bot.validated, bot.draft_revision]);
  const run = async () => { await validate(); reload(); };
  const errors = (report?.items ?? []).filter((i) => i.severity === "error");
  const warnings = (report?.items ?? []).filter((i) => i.severity !== "error");
  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="검증" description="초안을 엔진이 읽는 파일로 내보낸 뒤, 엔진의 로더로 그대로 읽어 봐요. 통과해야 게시할 수 있어요."
        actions={<Button variant="primary" icon={<ShieldCheck size={15} />} loading={validating} onClick={run}>지금 검증하기</Button>} />
      {error && <ErrorState error={error} onRetry={reload} what="검증 결과" />}
      {loading && <LoadingBlock rows={3} />}
      {!loading && !error && !report && (
        <EmptyState icon={<ShieldCheck size={20} />} title="아직 검증하지 않았어요" action={<Button variant="primary" loading={validating} onClick={run}>지금 검증하기</Button>}>
          서버를 다시 켜면 지난 결과는 사라져요. 한 번 검증해 보세요.
        </EmptyState>
      )}
      {report && (
        <div className="space-y-4">
          {!bot.validated && <Notice tone="warn" title="검증한 뒤에 초안이 바뀌었어요">아래 결과는 예전 초안 기준이에요. 다시 검증해 보세요.</Notice>}
          {report.ok ? (
            <Notice tone="ok" title="엔진이 이 상담봇을 그대로 읽을 수 있어요"
              action={bot.validated && bot.has_unpublished_changes ? <Button size="sm" variant="primary" onClick={openPublish}>게시하기</Button> : undefined}>
              {warnings.length ? `참고할 점이 ${warnings.length}개 있어요.` : "참고할 점도 없어요."}
            </Notice>
          ) : (
            <Notice tone="err" title={`고칠 곳이 ${errors.length}개 있어요`}>
              엔진은 파일마다 처음 만난 문제 하나만 알려 줘요. 하나를 고치면 같은 파일에서 다음 문제가 보일 수 있어요.
            </Notice>
          )}
          {report.items.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-line bg-surface">
              <table className="w-full text-sm">
                <thead className="bg-sunken text-left text-xs font-medium text-muted">
                  <tr><th scope="col" className="w-28 px-4 py-2.5">종류</th><th scope="col" className="w-64 px-4 py-2.5">고칠 곳</th><th scope="col" className="px-4 py-2.5">엔진이 남긴 말</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {report.items.map((i, k) => (
                    <tr key={k} className="align-top">
                      <td className="px-4 py-3">{i.severity === "error" ? <StatusChip tone="err">문제</StatusChip> : <StatusChip tone="warn">참고</StatusChip>}</td>
                      <td className="px-4 py-3"><Where bot={bot} file={i.file} flow={i.flow_id} node={i.node_id} /></td>
                      <td className="px-4 py-3 text-ink-2"><span className="break-words">{i.message}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
