import { Rocket } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Bot, type Publication, type Report } from "../api";
import { botName } from "../copy";
import { useShell } from "../hooks";
import type { Comparison, SiblingCheck } from "../lib/changes";
import { paths } from "../paths";
import { Button, Dialog, Disclosure, Field, Input, LoadingBlock, Notice, useToast } from "../ui";
import { ChangeSummary, SiblingWarnings } from "./ChangeSummary";

/** Publish: what changed since the last version, the sibling warnings (they never block), a note. */
export default function PublishDialog({ bot, onClose }: { bot: Bot; onClose: () => void }) {
  const { refresh } = useShell();
  const toast = useToast();
  const nav = useNavigate();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [message, setMessage] = useState("");
  const [changes, setChanges] = useState<Comparison | null>(null);
  const [siblings, setSiblings] = useState<SiblingCheck | null>(null);
  const [loadFail, setLoadFail] = useState("");
  useEffect(() => {
    let alive = true;
    api.get<Comparison>(`/bots/${bot.slug}/changes`).then((c) => alive && setChanges(c)).catch((e) => alive && setLoadFail((e as Error).message));
    api.get<SiblingCheck>(`/bots/${bot.slug}/siblings/check`).then((c) => alive && setSiblings(c)).catch(() => { /* a warning list is optional */ });
    return () => { alive = false; };
  }, [bot.slug]);
  const nothing = !!changes && changes.base.kind !== "none" && changes.summary.empty;
  const publish = async () => {
    setBusy(true); setMessage(""); setReport(null);
    try {
      const p = await api.post<Publication>(`/bots/${bot.slug}/publications`, { note });
      refresh(); onClose(); toast(`${p.number}번째로 게시했어요`);
      nav(paths.bot(bot.slug, "history"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) { setReport(e.body.report); refresh(); setMessage("엔진이 이 초안을 받아들이지 않아 게시하지 않았어요. 아래를 고친 뒤 다시 게시해 보세요."); }
      else if (e instanceof ApiError && e.status === 409) setMessage("마지막 게시와 내용이 같아서 게시할 것이 없어요.");
      else setMessage((e as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onClose={onClose} title={`${botName(bot)} 게시하기`}
      footer={<><Button onClick={onClose}>취소</Button><Button variant="primary" loading={busy} disabled={nothing} icon={<Rocket size={15} />} onClick={publish}>게시하기</Button></>}>
      <p className="mb-4 text-sm text-ink-2">엔진 검사를 한 번 더 거친 뒤 지금 초안을 {bot.last_published_number + 1}번째 버전으로 저장하고 엔진이 읽는 파일로 내보내요. 게시한 버전은 바뀌지 않아요. 보관하는 버전은 최근 5개예요.</p>
      <div className="mb-4">
        <h3 className="mb-2 text-sm font-semibold text-ink">{changes?.base.kind === "publication" ? `${changes.base.number}번째 버전에서 바뀐 것` : "이번에 게시할 내용"}</h3>
        {!changes && !loadFail && <LoadingBlock rows={2} />}
        {loadFail && <Notice tone="warn" title="바뀐 내용을 불러오지 못했어요">{loadFail}</Notice>}
        {nothing && <Notice tone="idle" title="마지막 게시와 내용이 같아서 게시할 것이 없어요" />}
        {changes && !nothing && <div className="max-h-64 overflow-y-auto pr-1"><ChangeSummary data={changes} /></div>}
      </div>
      {siblings && siblings.warning_count > 0 && (
        <div className="mb-4">
          <Disclosure defaultOpen title="다른 언어 봇과 구조가 달라요" badge={<span className="num text-xs text-warn-fg">{siblings.warning_count}</span>}
            summary="게시는 그대로 할 수 있어요">
            <SiblingWarnings check={siblings} />
          </Disclosure>
        </div>
      )}
      <Field label="무엇을 바꿨나요?" optional hint="게시 이력에 남아요.">
        <Input data-autofocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="예: 재질문 횟수를 3번으로 늘림" />
      </Field>
      {message && <div className="mt-4"><Notice tone={report ? "err" : "warn"} title={message} /></div>}
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
