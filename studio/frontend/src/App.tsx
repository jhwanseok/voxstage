import {
  AudioLines, BookOpenText, Database, GitBranch, History as HistoryIcon, LayoutDashboard, PlugZap, Rocket, ShieldCheck,
} from "lucide-react";
import { lazy, Suspense, useState, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { BotActionsContext } from "./actions";
import { ApiError, api, type Bot, type Publication, type Report } from "./api";
import { botName, botStatus, langName } from "./copy";
import { ShellContext, useFetch, useShell } from "./hooks";
import { paths, type BotSection } from "./paths";
import { Button, cn, Dialog, ErrorState, Field, Input, LoadingBlock, Notice, StatusChip, ToastProvider, useToast } from "./ui";
import FaqPage from "./pages/Faq";
import FlowEditor from "./pages/FlowEditor";
import Flows from "./pages/Flows";
import History from "./pages/History";
import Home from "./pages/Home";
import Overview from "./pages/Overview";
import DataPage from "./pages/Data";
import Tools from "./pages/Tools";
import Validation from "./pages/Validation";

// Design mockups (static data): /mock/home, /mock/faq, /mock/flow. Loaded lazily, kept as the design reference.
const MockLayout = lazy(() => import("./mock/MockLayout"));
const MockHome = lazy(() => import("./mock/Home"));
const MockFaq = lazy(() => import("./mock/Faq"));
const MockFlow = lazy(() => import("./mock/Flow"));

const MENU: { section: BotSection; label: string; icon: typeof LayoutDashboard }[] = [
  { section: "overview", label: "개요", icon: LayoutDashboard },
  { section: "faq", label: "자주 묻는 질문", icon: BookOpenText },
  { section: "flows", label: "시나리오", icon: GitBranch },
  { section: "data", label: "데이터", icon: Database },
  { section: "tools", label: "API 연결", icon: PlugZap },
  { section: "validation", label: "검증", icon: ShieldCheck },
  { section: "history", label: "게시 이력", icon: HistoryIcon },
];

function PublishDialog({ bot, onClose }: { bot: Bot; onClose: () => void }) {
  const { refresh } = useShell();
  const toast = useToast();
  const nav = useNavigate();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [message, setMessage] = useState("");
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
      footer={<><Button onClick={onClose}>취소</Button><Button variant="primary" loading={busy} icon={<Rocket size={15} />} onClick={publish}>게시하기</Button></>}>
      <p className="mb-4 text-sm text-ink-2">엔진 검사를 한 번 더 거친 뒤 지금 초안을 {bot.last_published_number + 1}번째 버전으로 저장하고 엔진이 읽는 파일로 내보내요. 게시한 버전은 바뀌지 않아요.</p>
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

function Sidebar({ bot }: { bot?: Bot }) {
  const { bots } = useShell();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const section = (pathname.split("/")[3] ?? "overview") as BotSection;
  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-line bg-surface max-md:hidden">
      <NavLink to={paths.home()} className="flex items-center gap-2.5 px-5 py-4">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-on-brand"><AudioLines size={18} aria-hidden /></span>
        <span className="text-[15px] font-bold tracking-tight text-ink">보이스봇 스튜디오</span>
      </NavLink>
      {bot && (
        <>
          <div className="mx-3 mb-3">
            <label htmlFor="bot-switch" className="mb-1 block px-1 text-xs text-muted">상담봇</label>
            <select id="bot-switch" value={bot.slug} onChange={(e) => nav(paths.bot(e.target.value, section))}
              className="h-10 w-full rounded-lg border border-line bg-surface px-2.5 text-sm font-semibold text-ink">
              {bots.map((b) => <option key={b.slug} value={b.slug}>{botName(b)} ({langName(b.lang)})</option>)}
            </select>
          </div>
          <nav aria-label="상담봇 메뉴" className="flex flex-col gap-0.5 px-3">
            {MENU.map(({ section: s, label, icon: Icon }) => (
              <NavLink key={s} to={paths.bot(bot.slug, s)} end={s !== "flows"}
                className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
                  isActive ? "bg-brand-50 font-semibold text-brand-700" : "text-ink-2 hover:bg-sunken hover:text-ink")}>
                <Icon size={17} aria-hidden />{label}
              </NavLink>
            ))}
          </nav>
        </>
      )}
      <div className="mt-auto border-t border-line px-5 py-4 text-xs text-muted">
        <div className="font-medium text-ink-2">로컬 사용자</div>
        편집과 게시를 모두 할 수 있어요
      </div>
    </aside>
  );
}

function Frame({ bot, header, children }: { bot?: Bot; header: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-ground">
      <Sidebar bot={bot} />
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-6 backdrop-blur max-md:px-4">{header}</header>
        {bot && (
          <nav aria-label="상담봇 메뉴" className="flex gap-1 overflow-x-auto border-b border-line bg-surface px-3 py-1.5 md:hidden">
            <NavLink to={paths.home()} className="whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] text-ink-2">목록</NavLink>
            {MENU.map(({ section: s, label }) => (
              <NavLink key={s} to={paths.bot(bot.slug, s)} end={s !== "flows"}
                className={({ isActive }) => cn("whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px]", isActive ? "bg-brand-50 font-semibold text-brand-700" : "text-ink-2")}>{label}</NavLink>
            ))}
          </nav>
        )}
        {children}
      </div>
    </div>
  );
}

function BotShell() {
  const { bot: slug } = useParams();
  const { bots, botsError, botsLoading, refresh } = useShell();
  const toast = useToast();
  const nav = useNavigate();
  const [publishing, setPublishing] = useState(false);
  const [validating, setValidating] = useState(false);
  const bot = bots.find((b) => b.slug === slug);
  if (!bot) {
    return (
      <Frame header={<span className="text-sm text-muted">상담봇</span>}>
        <main className="p-8">
          {botsError ? <ErrorState error={botsError} onRetry={refresh} what="상담봇 목록" />
            : botsLoading || !bots.length ? <LoadingBlock /> : <Notice tone="warn" title={`${slug} 상담봇이 없어요`}>목록에서 다른 상담봇을 골라 보세요.</Notice>}
        </main>
      </Frame>
    );
  }
  const st = botStatus(bot);
  const validate = async (goToProblems = true): Promise<Report | null> => {
    setValidating(true);
    try {
      const r = await api.post<Report>(`/bots/${bot.slug}/validate`);
      refresh();
      toast(r.ok ? "검증을 통과했어요" : `고칠 곳이 ${r.items.filter((i) => i.severity === "error").length}개 있어요`, r.ok ? "ok" : "err");
      if (!r.ok && goToProblems) nav(paths.bot(bot.slug, "validation"));
      return r;
    } catch (e) { toast((e as Error).message, "err"); return null; }
    finally { setValidating(false); }
  };
  const actions = { validate: () => validate(false), openPublish: () => setPublishing(true), validating };
  return (
    <Frame bot={bot} header={
      <>
        <span className="truncate text-base font-semibold text-ink">{botName(bot)}</span>
        <span className="text-xs text-muted">{langName(bot.lang)}</span>
        <StatusChip tone={st.tone}>{st.text}</StatusChip>
        <span className="flex-1" />
        <Button icon={<ShieldCheck size={15} />} loading={validating} onClick={() => void validate()}>검증하기</Button>
        <Button variant="primary" icon={<Rocket size={15} />} onClick={() => setPublishing(true)}>게시하기</Button>
      </>
    }>
      <BotActionsContext.Provider value={actions}>
      <Routes>
        <Route index element={<Navigate to={paths.bot(bot.slug)} replace />} />
        <Route path="overview" element={<Overview bot={bot} />} />
        <Route path="faq" element={<FaqPage bot={bot} />} />
        <Route path="flows" element={<Flows bot={bot} />} />
        <Route path="flows/:flowId" element={<FlowEditor bot={bot} />} />
        <Route path="data" element={<DataPage bot={bot} />} />
        <Route path="tools" element={<Tools bot={bot} />} />
        <Route path="validation" element={<Validation bot={bot} />} />
        <Route path="history" element={<History bot={bot} />} />
        <Route path="*" element={<Navigate to={paths.bot(bot.slug)} replace />} />
      </Routes>
      </BotActionsContext.Provider>
      {publishing && <PublishDialog bot={bot} onClose={() => setPublishing(false)} />}
    </Frame>
  );
}

export default function App() {
  const [version, setVersion] = useState(0);
  const { data: bots, error, loading } = useFetch<Bot[]>("/bots", [version]);
  const shell = { bots: bots ?? [], botsError: error, botsLoading: loading, refresh: () => setVersion((v) => v + 1), version };
  return (
    <ToastProvider>
      <ShellContext.Provider value={shell}>
        <Routes>
          <Route path="/" element={<Frame header={<span className="text-base font-semibold text-ink">상담봇</span>}><Home /></Frame>} />
          <Route path="/b/:bot/*" element={<BotShell />} />
          <Route path="/mock" element={<Suspense fallback={null}><MockLayout /></Suspense>}>
            <Route index element={<Navigate to={paths.mock()} replace />} />
            <Route path="home" element={<Suspense fallback={null}><MockHome /></Suspense>} />
            <Route path="faq" element={<Suspense fallback={null}><MockFaq /></Suspense>} />
            <Route path="flow" element={<Suspense fallback={null}><MockFlow /></Suspense>} />
            <Route path="*" element={<Navigate to={paths.mock()} replace />} />
          </Route>
          <Route path="*" element={<Navigate to={paths.home()} replace />} />
        </Routes>
      </ShellContext.Provider>
    </ToastProvider>
  );
}
