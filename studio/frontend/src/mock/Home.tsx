import { BookOpenText, Clock, GitBranch, Plus, PlugZap, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { StatusChip } from "./MockLayout";

const BOTS = [
  { name: "은행 상담봇", lang: "한국어", slug: "bank-ko", faq: 8, flows: 9, apis: 5, last: "오늘 14:20 · 3번째 게시", state: { tone: "warn" as const, text: "게시 안 된 변경 3건" } },
  { name: "Bank assistant", lang: "English", slug: "bank-en", faq: 8, flows: 9, apis: 5, last: "어제 18:02 · 2번째 게시", state: { tone: "ok" as const, text: "게시됨" } },
  { name: "쇼핑몰 상담봇", lang: "한국어", slug: "shop-ko", faq: 8, flows: 8, apis: 4, last: "게시한 적 없음", state: { tone: "err" as const, text: "검증 필요" } },
  { name: "통신사 상담봇", lang: "한국어", slug: "telecom-ko", faq: 8, flows: 7, apis: 4, last: "10월 25일 · 1번째 게시", state: { tone: "ok" as const, text: "게시됨" } },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">안녕하세요, 오늘은 어떤 상담봇을 다듬어 볼까요?</h2>
          <p className="mt-1 text-sm text-slate-500">상담봇 하나는 업종 하나와 언어 하나로 이루어져요. 질문·시나리오·API 연결을 고치고, 검증한 뒤 게시하면 음성봇 엔진이 바로 읽어 가요.</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium hover:bg-slate-50"><Upload size={15} />기존 데이터 가져오기</button>
          <button className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-brand-500 px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-600"><Plus size={15} />새 상담봇</button>
        </div>
      </div>

      <div className="mb-8 grid grid-cols-3 gap-4">
        {[["상담봇", "4개", "한국어 3 · 영어 1"], ["게시 대기", "2개", "변경이 있거나 검증이 필요해요"], ["최근 게시", "오늘 14:20", "은행 상담봇 3번째"]].map(([k, v, s]) => (
          <div key={k} className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="text-xs font-medium text-slate-500">{k}</div>
            <div className="mt-1 text-2xl font-bold">{v}</div>
            <div className="mt-0.5 text-xs text-slate-500">{s}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-5">
        {BOTS.map((b) => (
          <Link to="/mock/faq" key={b.slug} className="group rounded-xl border border-slate-200 bg-white p-5 transition hover:border-brand-500 hover:shadow-md">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-lg font-semibold group-hover:text-brand-700">{b.name}</div>
                <div className="mt-0.5 text-xs text-slate-500">{b.lang} · <span className="font-mono">{b.slug}</span></div>
              </div>
              <StatusChip tone={b.state.tone}>{b.state.text}</StatusChip>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-3 text-sm">
              <div className="flex items-center gap-2 whitespace-nowrap text-slate-700"><BookOpenText size={16} className="text-slate-400" /><span><b>{b.faq}</b>개 질문</span></div>
              <div className="flex items-center gap-2 whitespace-nowrap text-slate-700"><GitBranch size={16} className="text-slate-400" /><span><b>{b.flows}</b>개 시나리오</span></div>
              <div className="flex items-center gap-2 whitespace-nowrap text-slate-700"><PlugZap size={16} className="text-slate-400" /><span><b>{b.apis}</b>개 API</span></div>
            </div>
            <div className="mt-4 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-xs text-slate-500"><Clock size={13} />{b.last}</div>
          </Link>
        ))}
      </div>
    </main>
  );
}
