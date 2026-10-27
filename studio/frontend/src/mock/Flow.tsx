import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { Zap, CheckCircle2, Flag, HelpCircle, MessageSquare, PhoneOff, PlugZap, Play, Plus, ShieldAlert, ListChecks } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "./MockLayout";

const KIND = {
  say: { label: "말하기", icon: MessageSquare, bar: "bg-sky-500", soft: "bg-sky-50 text-sky-700" },
  ask: { label: "고객에게 묻기", icon: HelpCircle, bar: "bg-amber-500", soft: "bg-amber-50 text-amber-700" },
  confirm: { label: "예/아니오 확인", icon: ListChecks, bar: "bg-pink-500", soft: "bg-pink-50 text-pink-700" },
  call: { label: "API 호출", icon: PlugZap, bar: "bg-emerald-500", soft: "bg-emerald-50 text-emerald-700" },
  end: { label: "끝내기", icon: PhoneOff, bar: "bg-slate-500", soft: "bg-slate-100 text-slate-700" },
} as const;

interface D extends Record<string, unknown> { kind: keyof typeof KIND; id: string; text: string; waits?: boolean; risky?: boolean; exits: { id: string; label: string }[] }

function Card({ data, selected }: NodeProps<Node<D>>) {
  const k = KIND[data.kind]; const Icon = k.icon;
  return (
    <div className={`w-[300px] overflow-hidden rounded-xl bg-white shadow-sm ring-1 ${selected ? "ring-2 ring-brand-500" : "ring-slate-200"}`}>
      <Handle type="target" position={Position.Top} id="in" />
      <div className={`h-1.5 ${k.bar}`} />
      <div className="px-4 pb-3 pt-3">
        <div className="flex items-center justify-between">
          <span className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold ${k.soft}`}><Icon size={13} />{k.label}</span>
          <span className="flex gap-1">
            {data.waits && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">답을 기다림</span>}
            {data.risky && <span className="inline-flex items-center gap-0.5 rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-600"><ShieldAlert size={10} />되돌릴 수 없음</span>}
          </span>
        </div>
        <div className="mt-2 text-[15px] font-semibold leading-snug">{data.text}</div>
        <div className="mt-1 font-mono text-[11px] text-slate-500">{data.id}</div>
      </div>
      {data.exits.length > 0 && (
        <div className="flex justify-around border-t border-slate-100 pb-1 pt-1.5">
          {data.exits.map((e) => (
            <div key={e.id} className="relative px-3 py-1 text-xs font-semibold text-slate-600">
              {e.label}<Handle type="source" position={Position.Bottom} id={e.id} style={{ bottom: -6 }} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function TriggerCard(_: NodeProps) {
  return (
    <div className="w-[300px] overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-brand-500/40">
      <div className="h-1.5 bg-brand-500" />
      <div className="px-4 pb-3 pt-3">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700"><Zap size={13} />이런 말을 들으면 시작해요</span>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="font-semibold text-emerald-700">포함</span>{["이체", "송금"].map((w) => <span key={w} className="rounded-md bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700">{w}</span>)}
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="font-semibold text-rose-700">제외</span>{["수수료", "한도", "해외", "정기"].map((w) => <span key={w} className="rounded-md bg-rose-50 px-2 py-0.5 font-medium text-rose-700">{w}</span>)}
          <span className="text-slate-500">외 1</span>
        </div>
      </div>
      <div className="relative border-t border-slate-100 py-1.5 text-center text-xs font-semibold text-slate-600">다음 단계로<Handle type="source" position={Position.Bottom} id="next" style={{ bottom: -6 }} /></div>
    </div>
  );
}
function StartPill(_: NodeProps) {
  return <div className="inline-flex items-center gap-1.5 rounded-full bg-brand-500 px-4 py-2 text-sm font-semibold text-white shadow"><Play size={13} />시작<Handle type="source" position={Position.Bottom} id="next" /></div>;
}
const nodeTypes = { card: Card, start: TriggerCard };

const N = (id: string, x: number, y: number, d: { kind: keyof typeof KIND; text: string; waits?: boolean; risky?: boolean; exits: { id: string; label: string }[] }): Node<D> => ({ id, type: "card", position: { x, y }, data: { id, ...d } });
const nodes: Node<any>[] = [
  { id: "start", type: "start", position: { x: 0, y: -170 }, data: {} as any },
  N("ask_amount", 0, 0, { kind: "ask", text: "이체할 금액을 말씀해 주세요.", waits: true, exits: [{ id: "next", label: "다음" }] }),
  N("ask_to", 0, 190, { kind: "ask", text: "저축 계좌와 입출금 계좌 중 어느 쪽으로 보낼까요?", waits: true, exits: [{ id: "next", label: "다음" }] }),
  N("confirm", 0, 380, { kind: "confirm", text: "{금액}원을 {받는 계좌} 계좌로 보낼까요?", waits: true, exits: [{ id: "yes", label: "예" }, { id: "no", label: "아니오" }] }),
  N("make", -20, 590, { kind: "call", text: "이체 실행 (make_transfer)", risky: true, exits: [{ id: "ok", label: "성공" }, { id: "error", label: "실패" }] }),
  N("say_done", -190, 790, { kind: "say", text: "이체했어요. 확인 번호는 {확인 번호}입니다.", exits: [{ id: "next", label: "다음" }] }),
  N("say_fail", 170, 790, { kind: "say", text: "지금은 이체를 할 수 없어요. 잠시 뒤 다시 시도해 주세요.", exits: [{ id: "next", label: "다음" }] }),
  N("done", 0, 990, { kind: "end", text: "시나리오 끝", exits: [] }),
];
const E = (s: string, h: string, t: string, label?: string, color = "#94a3b8"): Edge => ({
  id: `${s}:${h}`, source: s, sourceHandle: h, target: t, targetHandle: "in", type: "smoothstep", label,
  markerEnd: { type: MarkerType.ArrowClosed, color }, style: { stroke: color, strokeWidth: 1.8 },
  labelStyle: { fill: color, fontWeight: 700 }, labelBgStyle: { fill: "#fff" }, labelBgPadding: [6, 3],
});
const edges: Edge[] = [
  { ...E("start", "next", "ask_amount"), targetHandle: "in" },
  E("ask_amount", "next", "ask_to"), E("ask_to", "next", "confirm"),
  E("confirm", "yes", "make", "예", "#16a34a"), E("confirm", "no", "done", "아니오", "#e11d48"),
  E("make", "ok", "say_done", "성공", "#16a34a"), E("make", "error", "say_fail", "실패", "#e11d48"),
  E("say_done", "next", "done"), E("say_fail", "next", "done"),
];

export default function FlowMock() {
  const [tab, setTab] = useState<"node" | "flow">("node");
  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <div className="relative min-w-0 flex-1">
        <div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-xl bg-white/95 px-3 py-2 shadow ring-1 ring-slate-200">
          <span className="text-sm font-semibold">이체하기</span><span className="font-mono text-xs text-slate-500">transfer</span>
          <span className="mx-1 h-4 w-px bg-slate-200" />
          <StatusChip tone="ok"><CheckCircle2 size={12} />문제 없음</StatusChip>
          <span className="text-xs text-slate-500">노드 7개 · 보기 전용</span>
        </div>
        <div className="absolute right-4 top-4 z-10 flex gap-2">
          <button className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium shadow ring-1 ring-slate-200 hover:bg-slate-50">자동 정렬</button>
          <button className="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-slate-500 shadow ring-1 ring-slate-200"><Plus size={14} />노드 추가</button>
        </div>
        <ReactFlow nodes={nodes.map((n) => ({ ...n, selected: n.id === "confirm" }))} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.1, minZoom: 0.5, maxZoom: 1 }}
          nodesConnectable={false} proOptions={{ hideAttribution: false }} style={{ background: "#f3f4f8" }}>
          <Background gap={22} color="#dfe2ea" />
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap pannable zoomable position="bottom-right" nodeColor="#cbd5e1" maskColor="rgba(243,244,248,.7)" />
        </ReactFlow>
      </div>

      <aside className="w-[360px] shrink-0 overflow-y-auto border-l border-slate-200 bg-white">
        <div className="flex border-b border-slate-200 text-sm font-medium">
          {([["node", "선택한 단계"], ["flow", "시나리오 설정"]] as const).map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} className={`flex-1 px-4 py-3 ${tab === k ? "border-b-2 border-brand-500 text-brand-700" : "text-slate-500"}`}>{l}</button>
          ))}
        </div>
        {tab === "node" ? (
          <div className="space-y-5 p-5">
            <div><span className="inline-flex items-center gap-1.5 rounded-md bg-pink-50 px-2 py-0.5 text-xs font-semibold text-pink-700"><ListChecks size={13} />예/아니오 확인</span>
              <div className="mt-2 font-mono text-xs text-slate-500">confirm</div></div>
            <div><label className="mb-1 block text-sm font-medium">고객에게 하는 말</label>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="rounded bg-brand-50 px-1 text-brand-700">{"{금액}"}</span>원을 <span className="rounded bg-brand-50 px-1 text-brand-700">{"{받는 계좌}"}</span> 계좌로 보낼까요?</div>
              <p className="mt-1 text-xs text-slate-500">보라색 부분은 고객이 앞에서 답한 값으로 바뀌어요.</p></div>
            <div><div className="mb-1 text-sm font-medium">답에 따라 이어지는 곳</div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"><span className="font-medium text-emerald-600">예</span><span>이체 실행 <span className="font-mono text-xs text-slate-500">make</span></span></div>
                <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"><span className="font-medium text-rose-600">아니오</span><span>시나리오 끝 <span className="font-mono text-xs text-slate-500">done</span></span></div>
              </div></div>
            <div className="flex gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800"><Flag size={14} className="mt-0.5 shrink-0" /><span>돈이 움직이는 API(이체 실행)는 반드시 이 확인 단계의 “예” 다음에만 호출할 수 있어요. 엔진이 게시 전에 검사해요.</span></div>
          </div>
        ) : (
          <div className="space-y-5 p-5">
            <div><div className="mb-1 text-sm font-medium">이 시나리오를 시작하는 말</div>
              <div className="space-y-2 text-sm">
                <div><span className="mr-2 text-xs font-semibold text-emerald-700">포함</span>{["이체", "송금"].map((w) => <span key={w} className="mr-1 rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">{w}</span>)}</div>
                <div><span className="mr-2 text-xs font-semibold text-rose-700">제외</span>{["수수료", "한도", "해외", "정기", "방법"].map((w) => <span key={w} className="mr-1 rounded-md bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700">{w}</span>)}</div>
              </div></div>
            <div><div className="mb-1 text-sm font-medium">처음 들은 말에서 미리 채우는 값</div>
              <div className="flex flex-wrap gap-1.5 text-xs"><span className="rounded-md bg-slate-100 px-2 py-0.5">금액 ← 숫자</span><span className="rounded-md bg-slate-100 px-2 py-0.5">받는 계좌 ← 저축 / 입출금</span></div></div>
            <div><div className="mb-1 text-sm font-medium">사용하는 API</div><div className="flex items-center gap-1.5 text-sm"><PlugZap size={14} className="text-emerald-600" />이체 실행 <span className="font-mono text-xs text-slate-500">make_transfer</span></div></div>
          </div>
        )}
      </aside>
    </div>
  );
}
