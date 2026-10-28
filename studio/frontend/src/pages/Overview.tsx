import { BookOpenText, GitBranch, PlugZap } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type Bot, type BotDetail, type BotSettings, type EngineSettings, type OnExceed } from "../api";
import { botName, domainName, langName, ON_EXCEED } from "../copy";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import { paths } from "../paths";
import { Button, cn, ErrorState, Field, Input, LoadingBlock, Notice, PageHeader, Select, StatusChip, useToast } from "../ui";

/** What to do next, from the bot status, with the one button that does it. */
function NextStep({ bot }: { bot: Bot }) {
  if (bot.validated && !bot.valid)
    return <Notice tone="err" title="엔진이 받아들이지 않는 곳이 있어요" action={<Link className="text-sm font-semibold text-err-fg underline-offset-2 hover:underline" to={paths.bot(bot.slug, "validation")}>고칠 곳 보기</Link>}>고친 뒤 다시 검증해 보세요.</Notice>;
  if (bot.has_unpublished_changes && !bot.validated)
    return <Notice tone="warn" title="게시하지 않은 변경이 있어요">위의 <b>검증하기</b>로 엔진이 읽을 수 있는지 먼저 확인해 보세요.</Notice>;
  if (bot.has_unpublished_changes)
    return <Notice tone="ok" title="검증을 통과했어요">위의 <b>게시하기</b>를 누르면 엔진이 새 버전을 읽어요.</Notice>;
  return <Notice tone="idle" title={bot.last_published_number ? `${bot.last_published_number}번째 버전이 엔진에 나가 있어요` : "아직 게시한 버전이 없어요"}>초안이 마지막 게시와 같아요.</Notice>;
}

function Section({ title, description, children, tag }: { title: string; description: string; children: ReactNode; tag?: ReactNode }) {
  return (
    <fieldset className="grid gap-x-8 gap-y-3 border-t border-line py-6 first:border-t-0 first:pt-0 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
      <legend className="sr-only">{title}</legend>
      <div>
        <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-ink" aria-hidden>{title}{tag}</div>
        <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function Count({ label, value, min, unit = "번", onChange, hint }: { label: string; value: number; min: number; unit?: string; onChange: (n: number) => void; hint?: string }) {
  const bad = !Number.isInteger(value) || value < min;
  return (
    <Field label={label} hint={hint} error={bad ? `${min} 이상의 정수를 넣어 주세요` : null}>
      <div className="relative">
        <Input type="number" inputMode="numeric" min={min} value={Number.isNaN(value) ? "" : value}
          onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} className="num pr-10" />
        <span className="pointer-events-none absolute right-3 top-2 text-sm text-muted" aria-hidden>{unit}</span>
      </div>
    </Field>
  );
}

function Action({ label, value, onChange }: { label: string; value: OnExceed; onChange: (v: OnExceed) => void }) {
  return (
    <Field label={label}>
      <Select value={value} onChange={(e) => onChange(e.target.value as OnExceed)}>
        {(Object.keys(ON_EXCEED) as OnExceed[]).map((k) => <option key={k} value={k}>{ON_EXCEED[k]}</option>)}
      </Select>
    </Field>
  );
}

const NotInEngine = () => <StatusChip tone="idle">스튜디오에만 저장</StatusChip>;

function SettingsForm({ bot, initial, onSaved }: { bot: Bot; initial: BotSettings; onSaved: (s: BotSettings) => void }) {
  const { refresh } = useShell();
  const toast = useToast();
  const [s, setS] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setS(initial), [initial]);
  const dirty = JSON.stringify(s) !== JSON.stringify(initial);
  useUnsavedWarning(dirty);

  const eng = <K extends keyof EngineSettings>(k: K, v: Partial<EngineSettings[K]>) =>
    setS((x) => ({ ...x, engine: { ...x.engine, [k]: { ...x.engine[k], ...v } } }));
  const studio = (v: Partial<BotSettings["studio_only"]>) => setS((x) => ({ ...x, studio_only: { ...x.studio_only, ...v } }));
  const e = s.engine;
  const invalid = Object.values(e).some((sec) => Object.values(sec).some((v) => typeof v === "number" && !Number.isInteger(v)))
    || !s.title.trim() || !/^[0-9+\-() ]*$/.test(s.studio_only.handoff_number ?? "");
  const engineChanged = JSON.stringify(s.engine) !== JSON.stringify(initial.engine);

  const save = async () => {
    setBusy(true); setError("");
    try {
      const out = await api.put<BotSettings>(`/bots/${bot.slug}/settings`, {
        title: s.title, engine: s.engine, revision: s.revision,
        studio_only: { handoff_number: s.studio_only.handoff_number || null, policy: s.studio_only.policy },
      });
      onSaved(out); refresh();
      toast(engineChanged ? "저장했어요. 검증하고 게시하면 엔진에 반영돼요" : "저장했어요");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 새로 불러온 뒤 다시 고쳐 주세요." : (err as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={(ev) => { ev.preventDefault(); if (!invalid && dirty) void save(); }}
      className="rounded-2xl border border-line bg-surface">
      <div className="flex items-start gap-3 border-b border-line px-6 py-5">
        <div className="flex-1">
          <h2 className="text-[15px] font-semibold text-ink">기본 설정</h2>
          <p className="mt-0.5 text-[13px] text-muted">이 상담봇의 모든 시나리오와 질문에 똑같이 적용되는 값이에요.</p>
        </div>
      </div>
      <div className="px-6 py-6">
        <Section title="상담봇 정보" description="이름은 스튜디오에서만 보여요. 언어와 업종은 상담봇을 이루는 값이라 바꿀 수 없어요.">
          <Field label="이름"><Input value={s.title} onChange={(ev) => setS({ ...s, title: ev.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="언어"><Input value={langName(s.lang)} disabled /></Field>
            <Field label="업종"><Input value={domainName(s.domain)} disabled /></Field>
          </div>
        </Section>

        <Section title="다시 묻기" description="고객 답에서 필요한 값을 찾지 못했을 때 같은 질문을 몇 번 더 할지 정해요.">
          <Count label="기본 재질문 횟수" min={0} value={e.ask.max_reprompts} onChange={(n) => eng("ask", { max_reprompts: n })} hint="0이면 다시 묻지 않아요." />
          <Action label="그래도 못 받으면" value={e.ask.on_exceed} onChange={(v) => eng("ask", { on_exceed: v })} />
        </Section>

        <Section title="알아듣지 못했을 때" description="어느 질문과도 맞지 않는 말이 이어질 때예요. 맞는 말을 들으면 횟수는 처음부터 다시 세요.">
          <Count label="연속으로 허용하는 횟수" min={1} value={e.fallback.max_misses} onChange={(n) => eng("fallback", { max_misses: n })} />
          <Action label="넘으면" value={e.fallback.on_exceed} onChange={(v) => eng("fallback", { on_exceed: v })} />
        </Section>

        <Section title="고객이 값을 고칠 때" description="읽어 드린 값(금액, 번호 등)을 고객이 고쳐 말할 수 있는 횟수예요.">
          <Count label="고칠 수 있는 횟수" min={0} value={e.correction.max_corrections} onChange={(n) => eng("correction", { max_corrections: n })} />
          <Action label="넘으면" value={e.correction.on_exceed} onChange={(v) => eng("correction", { on_exceed: v })} />
        </Section>

        <Section title="본인 확인" description="본인 확인에 실패하면 통화를 잠그고 다음 단계로 넘겨요. 시나리오마다 따로 정할 수도 있어요.">
          <Count label="시도할 수 있는 횟수" min={1} value={e.verification.max_attempts} onChange={(n) => eng("verification", { max_attempts: n })} />
          <Action label="모두 실패하면" value={e.verification.on_exceed} onChange={(v) => eng("verification", { on_exceed: v })} />
        </Section>

        <Section title="API가 실패하거나 느릴 때" description="응답 제한 시간을 넘긴 호출은 실패로 세요. 통화 한 번 동안의 실패 횟수예요.">
          <Count label="허용하는 실패 횟수" min={1} value={e.tools.max_failures} onChange={(n) => eng("tools", { max_failures: n })} />
          <Count label="응답 제한 시간" min={1} unit="ms" value={e.tools.timeout_ms} onChange={(n) => eng("tools", { timeout_ms: n })} />
          <Action label="넘으면" value={e.tools.on_exceed} onChange={(v) => eng("tools", { on_exceed: v })} />
        </Section>

        <Section title="다른 문의로 넘어갈 때" description="진행 중인 시나리오를 잠시 미뤄 두고 다른 문의를 받을 때, 미뤄 둘 수 있는 개수예요. 넘으면 가장 오래된 것부터 버려요.">
          <Count label="미뤄 둘 수 있는 시나리오" min={1} unit="개" value={e.switch.max_parked} onChange={(n) => eng("switch", { max_parked: n })} />
        </Section>

        <Section title="상담사 연결 번호" tag={<NotInEngine />}
          description="엔진은 지금 '상담사에게 연결'이라는 동작만 내보내고 번호는 쓰지 않아요. 여기 적은 번호는 게시 파일에 들어가지 않아요.">
          <Field label="연결할 번호" optional error={/^[0-9+\-() ]*$/.test(s.studio_only.handoff_number ?? "") ? null : "숫자, 공백, + - ( ) 만 쓸 수 있어요"}>
            <Input inputMode="tel" value={s.studio_only.handoff_number ?? ""} placeholder="예: 1588-0000"
              onChange={(ev) => studio({ handoff_number: ev.target.value })} />
          </Field>
        </Section>

        <Section title="정책값" tag={<NotInEngine />}
          description="시나리오 문구에 들어가는 규칙 값이에요. 엔진은 통화를 시작할 때 받은 값을 쓰므로, 여기 값은 지금은 기록용이에요.">
          {s.policy_refs.length === 0 ? (
            <p className="text-sm text-muted sm:col-span-2">이 상담봇의 시나리오는 정책값을 쓰지 않아요.</p>
          ) : s.policy_refs.map((r) => (
            <Field key={r.key} label={<code className="text-[13px]">{r.key}</code>} optional hint={`쓰는 곳: ${r.flows.join(", ")}`}>
              <Input value={s.studio_only.policy[r.key] ?? ""} placeholder="값 없음"
                onChange={(ev) => studio({ policy: { ...s.studio_only.policy, [r.key]: ev.target.value } })} />
            </Field>
          ))}
        </Section>
      </div>
      <div className={cn("sticky bottom-0 flex items-center gap-3 rounded-b-2xl border-t border-line bg-surface/95 px-6 py-3 backdrop-blur", !dirty && "opacity-90")}>
        <span className="flex-1 text-[13px]" role="status">
          {error ? <span className="font-medium text-err-fg">{error}</span>
            : dirty ? <span className="text-warn-fg">저장하지 않은 변경이 있어요{engineChanged && ". 저장 후 검증과 게시가 필요해요"}</span>
            : <span className="text-muted">모든 변경을 저장했어요</span>}
        </span>
        <Button disabled={!dirty || busy} onClick={() => { setS(initial); setError(""); }}>되돌리기</Button>
        <Button type="submit" variant="primary" loading={busy} disabled={!dirty || invalid}>저장</Button>
      </div>
    </form>
  );
}

export default function Overview({ bot }: { bot: Bot }) {
  const { version } = useShell();
  const { data: detail } = useFetch<BotDetail>(`/bots/${bot.slug}`, [version]);
  const { data: settings, error, loading, reload, setData } = useFetch<BotSettings>(`/bots/${bot.slug}/settings`);
  const counts = detail?.counts;
  // imported bots are titled "bank (ko)"; the form shows the readable name, so a first save stores it
  const initial = useMemo(() => (settings ? { ...settings, title: botName(settings) } : null), [settings]);
  const tiles = [
    { to: paths.bot(bot.slug, "faq"), icon: BookOpenText, label: "자주 묻는 질문", n: counts?.faq },
    { to: paths.bot(bot.slug, "flows"), icon: GitBranch, label: "시나리오", n: counts?.flows },
    { to: paths.bot(bot.slug, "tools"), icon: PlugZap, label: "API 연결", n: counts?.tools },
  ];
  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="개요" description={`${botName(bot)}의 상태와 기본 설정이에요.`} />
      <div className="mb-6"><NextStep bot={bot} /></div>
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        {tiles.map(({ to, icon: Icon, label, n }) => (
          <Link key={to} to={to} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3.5 hover:border-brand-500">
            <Icon size={18} className="text-muted" aria-hidden />
            <span className="flex-1 text-sm text-ink-2">{label}</span>
            <span className="num text-lg font-semibold text-ink">{n ?? "–"}</span>
          </Link>
        ))}
      </div>
      {error && <ErrorState error={error} onRetry={reload} what="기본 설정" />}
      {loading && <LoadingBlock rows={6} label="기본 설정을 불러오는 중" />}
      {initial && <SettingsForm bot={bot} initial={initial} onSaved={(x) => setData(x)} />}
    </main>
  );
}
