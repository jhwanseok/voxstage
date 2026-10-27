import { AlertCircle, Plus, Search, Trash2, X } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "./MockLayout";

const ROWS = [
  { id: "bank.faq.hours", q: "영업시간이 어떻게 되나요?", a: "영업점은 평일 오전 9시부터 오후 4시까지 운영하고, 주말과 공휴일에는 쉽니다.", kw: ["영업", "시간", "몇 시"], state: "ok", changed: false },
  { id: "bank.faq.card_loss", q: "체크카드를 잃어버렸어요", a: "앱이나 고객센터에서 분실 신고를 하면 즉시 카드가 정지됩니다.", kw: ["카드", "분실", "도난"], state: "ok", changed: true },
  { id: "bank.faq.transfer_limit", q: "이체 한도는 얼마인가요?", a: "이체 한도는 계좌 종류와 인증 수단에 따라 달라지며, 앱의 한도 메뉴에서 확인하고 바꿀 수 있습니다.", kw: ["이체", "한도"], state: "ok", changed: true },
  { id: "bank.faq.password_locked", q: "비밀번호를 여러 번 틀려서 잠겼어요", a: "비밀번호 오류로 계정이 잠긴 경우, 본인 확인 후 앱에서 직접 재설정할 수 있습니다.", kw: ["비밀번호", "잠김", "초기화"], state: "warn", changed: true },
  { id: "bank.faq.statement_copy", q: "거래 내역서는 어디서 받나요?", a: "앱의 문서함에서 내려받거나, 신분증을 들고 영업점에서 출력할 수 있습니다.", kw: ["내역서", "명세서"], state: "ok", changed: false },
  { id: "bank.faq.recurring_payment", q: "자동이체를 바꾸거나 해지하고 싶어요", a: "앱의 자동이체 메뉴에서 변경하거나 해지할 수 있습니다.", kw: ["자동이체", "해지"], state: "ok", changed: false },
  { id: "bank.faq.international_transfer", q: "해외로 송금할 수 있나요?", a: "해외 송금은 앱의 해외송금 메뉴 또는 영업점에서 가능합니다.", kw: ["해외", "송금"], state: "ok", changed: false },
];

function Chips({ items, tone = "slate" }: { items: string[]; tone?: "slate" | "brand" | "rose" }) {
  const c = { slate: "bg-slate-100 text-slate-700", brand: "bg-brand-50 text-brand-700", rose: "bg-rose-50 text-rose-700" }[tone];
  return <>{items.map((w) => <span key={w} className={`rounded-md px-2 py-0.5 text-xs font-medium ${c}`}>{w}</span>)}</>;
}

function ChipInput({ label, hint, items, tone }: { label: string; hint: string; items: string[]; tone: "slate" | "brand" | "rose" }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline gap-2"><span className="text-sm font-medium">{label}</span><span className="text-xs text-slate-500">{hint}</span></div>
      <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5">
        {items.map((w) => (
          <span key={w} className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${{ slate: "bg-slate-100 text-slate-700", brand: "bg-brand-50 text-brand-700", rose: "bg-rose-50 text-rose-700" }[tone]}`}>{w}<X size={12} className="cursor-pointer opacity-60" /></span>
        ))}
        <input className="min-w-20 flex-1 bg-transparent text-sm outline-none" placeholder="단어 입력 후 Enter" />
      </div>
    </div>
  );
}

export default function Faq() {
  const [sel, setSel] = useState(ROWS[1].id);
  const row = ROWS.find((r) => r.id === sel)!;
  return (
    <div className="flex">
      <main className="min-w-0 flex-1 px-8 py-6">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="whitespace-nowrap text-xl font-bold">자주 묻는 질문 <span className="ml-1 text-sm font-medium text-slate-500">{ROWS.length}개</span></h2>
          <span className="flex-1" />
          <div className="relative w-72"><Search size={15} className="absolute left-3 top-2.5 text-slate-400" /><input className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-brand-500" placeholder="질문·답변 검색" /></div>
          <select className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"><option>전체</option><option>고친 항목만</option><option>문제 있는 항목만</option></select>
          <button className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-brand-500 px-3.5 py-2 text-sm font-semibold text-white hover:bg-brand-600"><Plus size={15} />질문 추가</button>
        </div>
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
              <tr><th className="px-4 py-2.5">질문</th><th className="px-4 py-2.5">답변</th><th className="px-4 py-2.5">매칭 키워드</th><th className="px-4 py-2.5">상태</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {ROWS.map((r) => (
                <tr key={r.id} onClick={() => setSel(r.id)} className={`cursor-pointer align-top hover:bg-slate-50 ${sel === r.id ? "bg-brand-50/60" : ""}`}>
                  <td className="w-[26%] px-4 py-3 font-medium">{r.q}</td>
                  <td className="w-[36%] px-4 py-3 text-slate-600"><span className="line-clamp-2">{r.a}</span></td>
                  <td className="px-4 py-3"><div className="flex flex-wrap gap-1"><Chips items={r.kw} /></div></td>
                  <td className="whitespace-nowrap px-4 py-3">{r.state === "warn" ? <StatusChip tone="err"><AlertCircle size={12} />예문 부족</StatusChip> : r.changed ? <StatusChip tone="warn">수정됨</StatusChip> : <span className="text-xs text-slate-400">게시됨</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>

      <aside className="sticky top-14 h-[calc(100vh-3.5rem)] w-[460px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-6">
        <div className="mb-4 flex items-start justify-between">
          <div><div className="text-xs text-slate-500">질문 수정</div><h3 className="text-lg font-bold">{row.q}</h3><div className="mt-0.5 font-mono text-xs text-slate-400">{row.id}</div></div>
          <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100"><X size={18} /></button>
        </div>
        <div className="space-y-5">
          <div><label className="mb-1 block text-sm font-medium">고객이 묻는 말</label><input defaultValue={row.q} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>
          <div><label className="mb-1 block text-sm font-medium">봇의 답변 <span className="text-xs font-normal text-slate-500">그대로 읽어 드려요</span></label><textarea defaultValue={row.a} rows={3} className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand-500" /></div>

          <section className="rounded-xl bg-slate-50 p-4">
            <h4 className="mb-1 text-sm font-semibold">이 질문으로 알아듣는 조건</h4>
            <p className="mb-3 text-xs text-slate-500">고객 말에 아래 조건이 모두 맞으면 이 답변을 해요.</p>
            <div className="space-y-3">
              <ChipInput label="반드시 포함" hint="각 줄에서 하나 이상" items={["카드, 체크카드", "분실, 잃어버, 도난, 정지"]} tone="brand" />
              <ChipInput label="이 중 하나라도 포함" hint="선택" items={[]} tone="slate" />
              <ChipInput label="들어 있으면 제외" hint="다른 질문과 헷갈릴 때" items={["명세서", "한도"]} tone="rose" />
            </div>
            <p className="mt-3 rounded-md bg-white px-3 py-2 text-xs text-slate-600 ring-1 ring-slate-200">“카드 분실했어요”는 맞고, “카드 한도가 궁금해요”는 제외돼요.</p>
          </section>

          <section>
            <div className="mb-1 flex items-center justify-between"><h4 className="text-sm font-semibold">예문 <span className="ml-1 text-xs font-normal text-slate-500">3개 이상 필요 · 지금 3개</span></h4></div>
            <p className="mb-2 text-xs text-slate-500">조건을 만들 때 이 예문들을 같이 보면서 확인하세요.</p>
            <ul className="space-y-1.5">
              {["카드를 잃어버렸는데 어떻게 하죠", "체크카드가 없어졌어요 정지시키고 싶어요", "누가 내 카드를 훔친 것 같아요"].map((t) => (
                <li key={t} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-1.5 text-sm">{t}<Trash2 size={14} className="text-slate-300" /></li>
              ))}
            </ul>
            <button className="mt-2 text-sm font-medium text-brand-600">+ 예문 추가</button>
          </section>

          <section>
            <h4 className="mb-1 text-sm font-semibold">음성 인식 오류 예시 <span className="ml-1 text-xs font-normal text-slate-500">1개 이상</span></h4>
            <ul className="space-y-1.5"><li className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm">체크 카드를 이어버렸어요</li></ul>
          </section>
        </div>
        <div className="sticky bottom-0 -mx-6 mt-6 flex items-center justify-between border-t border-slate-200 bg-white px-6 py-3">
          <button className="text-sm font-medium text-rose-600">삭제</button>
          <div className="flex gap-2"><button className="rounded-lg border border-slate-200 px-3.5 py-1.5 text-sm font-medium">취소</button><button className="rounded-lg bg-brand-500 px-3.5 py-1.5 text-sm font-semibold text-white">저장</button></div>
        </div>
      </aside>
    </div>
  );
}
