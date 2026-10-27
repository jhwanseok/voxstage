import { Bot, BookOpenText, ChevronsUpDown, GitBranch, History, LayoutDashboard, PlugZap, Rocket, ShieldCheck } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";
import "./mock.css";

const MENU = [
  { to: "/mock/home", label: "개요", icon: LayoutDashboard },
  { to: "/mock/faq", label: "자주 묻는 질문", icon: BookOpenText },
  { to: "/mock/flow", label: "시나리오", icon: GitBranch },
  { to: "/mock/api", label: "API 연결", icon: PlugZap },
  { to: "/mock/check", label: "검증", icon: ShieldCheck },
  { to: "/mock/history", label: "배포 이력", icon: History },
];

export function StatusChip({ tone, children }: { tone: "ok" | "warn" | "err" | "idle"; children: React.ReactNode }) {
  const c = {
    ok: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    warn: "bg-amber-50 text-amber-700 ring-amber-200",
    err: "bg-rose-50 text-rose-700 ring-rose-200",
    idle: "bg-slate-100 text-slate-600 ring-slate-200",
  }[tone];
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${c}`}>{children}</span>;
}

/** Sidebar with the bot switcher, top bar with the bot status and the two actions. */
export default function MockLayout() {
  const { pathname } = useLocation();
  const home = pathname === "/mock/home";
  return (
    <div className="mock-root flex">
      <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <Link to="/mock/home" className="flex items-center gap-2 px-5 py-4">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-500 text-white"><Bot size={18} /></span>
          <span className="text-[15px] font-bold tracking-tight">보이스봇 스튜디오</span>
        </Link>
        {!home && (
          <button className="mx-3 mb-2 flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-left hover:bg-slate-50">
            <span><span className="block text-[11px] text-slate-500">상담봇</span><span className="text-sm font-semibold">은행 상담봇 · 한국어</span></span>
            <ChevronsUpDown size={15} className="text-slate-500" />
          </button>
        )}
        <nav aria-label="주요 메뉴" className="mt-1 flex flex-col gap-0.5 px-3">
          {MENU.map(({ to, label, icon: Icon }) => {
            const active = pathname === to;
            return (
              <Link key={to} to={to} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${active ? "bg-brand-50 font-semibold text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}>
                <Icon size={17} />{label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto border-t border-slate-100 p-4 text-xs text-slate-500">
          <div className="font-medium text-slate-700">로컬 사용자</div>
          편집자 · 게시자
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-6 backdrop-blur">
          {home ? <h1 className="text-base font-semibold">상담봇</h1> : (
            <>
              <h1 className="text-base font-semibold">은행 상담봇</h1>
              <StatusChip tone="warn">게시 안 된 변경 3건</StatusChip>
              <StatusChip tone="ok">검증 통과</StatusChip>
            </>
          )}
          <span className="flex-1" />
          {!home && (
            <>
              <button className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-1.5 text-sm font-medium hover:bg-slate-50"><ShieldCheck size={15} />검증하기</button>
              <button className="inline-flex items-center gap-1.5 rounded-lg bg-brand-500 px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-brand-600"><Rocket size={15} />게시하기</button>
            </>
          )}
        </header>
        <Outlet />
      </div>
    </div>
  );
}
