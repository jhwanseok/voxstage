import { describe, siblingText, type Comparison, type FileDiff, type SiblingCheck } from "../lib/changes";
import { cn, Disclosure, Tag } from "../ui";

const STATUS: Record<FileDiff["status"], { text: string; tone: "ok" | "err" | "warn" }> = {
  added: { text: "추가", tone: "ok" }, removed: { text: "삭제", tone: "err" }, changed: { text: "바뀜", tone: "warn" },
};

function Lines({ text }: { text: string }) {
  return (
    <pre className="max-h-72 overflow-auto rounded-lg bg-sunken py-2 text-xs leading-relaxed">
      {text.split("\n").map((l, i) => (
        <div key={i} className={cn("px-3 font-mono whitespace-pre-wrap break-all",
          l.startsWith("+") && !l.startsWith("+++") && "bg-ok-bg text-ok-fg", l.startsWith("-") && !l.startsWith("---") && "bg-err-bg text-err-fg",
          (l.startsWith("@@") || l.startsWith("---") || l.startsWith("+++")) && "text-muted")}>{l || " "}</div>
      ))}
    </pre>
  );
}

/** What differs between two versions: a summary by meaning first, the text of every changed file under "자세히". */
export function ChangeSummary({ data }: { data: Comparison }) {
  const groups = describe(data.summary);
  return (
    <div className="space-y-4">
      {data.summary.empty
        ? <p className="text-sm text-muted">바뀐 것이 없어요.</p>
        : groups.map((g) => (
          <section key={g.title} aria-label={g.title}>
            <h3 className="mb-1 text-[13px] font-semibold text-ink">{g.title}</h3>
            <ul className="space-y-1 text-[13px] text-ink-2">{g.lines.map((l, i) => <li key={i} className="rounded-md bg-sunken px-2.5 py-1.5">{l}</li>)}</ul>
          </section>
        ))}
      {data.files.length > 0 && (
        <Disclosure title="자세히" summary={`바뀐 파일 ${data.files.length}개의 글자 비교`}>
          <div className="space-y-4">
            {data.files.map((f) => (
              <div key={f.path}>
                <div className="mb-1 flex items-center gap-2"><Tag tone={STATUS[f.status].tone}>{STATUS[f.status].text}</Tag><span className="truncate font-mono text-xs text-ink">{f.path}</span></div>
                <Lines text={f.unified} />
              </div>
            ))}
          </div>
        </Disclosure>
      )}
    </div>
  );
}

/** The sibling check as a list of short warnings (empty when the structures agree). */
export function SiblingWarnings({ check }: { check: SiblingCheck }) {
  return (
    <div className="space-y-3 text-[13px]">
      {check.siblings.map((s) => (
        <section key={s.bot} aria-label={`${s.bot} 비교`}>
          <h3 className="mb-1 font-semibold text-ink">비교한 봇: {s.bot} (같은 이름의 시나리오 {s.compared}개)</h3>
          {s.warnings.length === 0
            ? <p className="text-muted">구조가 같아요.</p>
            : <ul className="space-y-1 text-ink-2">{s.warnings.map((w, i) => <li key={i} className="rounded-md bg-sunken px-2.5 py-1.5">{siblingText(w)}</li>)}</ul>}
        </section>
      ))}
    </div>
  );
}
