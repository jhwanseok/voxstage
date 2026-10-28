import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  applyNodeChanges, Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, ReactFlowProvider, useReactFlow,
  type Edge, type Node, type NodeProps,
} from "@xyflow/react";
import { api, type Bot, type FlowDetail, type GraphNode, type Item, type Tool } from "../api";
import { useFetch } from "../hooks";
import { START_ID, autoLayout, exits } from "../lib/graph";

const WAITS = new Set(["ask", "form", "confirm"]);
const KINDS = ["say", "ask", "form", "confirm", "call", "branch", "notices", "goto", "end"];

function summary(n: GraphNode, risky: Set<string>): string {
  const d = n.data;
  switch (n.type) {
    case "say": return d.text;
    case "ask": return `${d.slot} (${d.extractor ?? "text"}) ${d.prompt}`;
    case "form": return `slots: ${(d.slots ?? []).map((s: any) => s.slot).join(", ")}`;
    case "confirm": return d.prompt;
    case "call": return `${d.tool}(${Object.keys(d.args ?? {}).join(", ")})`;
    case "branch": return `${(d.cases ?? []).length} cases`;
    case "notices": return d.ids ? d.ids.join(", ") : "all applicable notices";
    case "goto": return `→ ${d.next}`;
    case "end": return d.action ? `${d.action}${d.reason ? `: ${d.reason}` : ""}` : "end of flow";
    default: return "";
  }
}

interface NodeData extends Record<string, unknown> { gn: GraphNode; risky: boolean; errors: Item[]; text: string }

function FlowNode({ data, selected }: NodeProps<Node<NodeData>>) {
  const { gn, risky, errors, text } = data;
  const ex = exits(gn);
  return (
    <div className={`fnode k-${gn.type}${WAITS.has(gn.type) ? " waits" : ""}${selected ? " sel" : ""}${errors.length ? " err" : ""}`}>
      <Handle type="target" position={Position.Left} id="in" />
      <div className="kind"><span>{gn.type}{WAITS.has(gn.type) ? " · waits" : ""}</span>
        <span>{risky && <b style={{ color: "var(--err)" }}>risky </b>}{errors.length > 0 && <b style={{ color: "var(--err)" }}>● {errors.length}</b>}</span></div>
      <div className="nid">{gn.id}</div>
      <div className="sum" title={text}>{text}</div>
      {ex.map((e) => (
        <div className="exit" key={e.handle}>{e.label}<Handle type="source" position={Position.Right} id={e.handle} /></div>
      ))}
    </div>
  );
}

function StartNode() {
  return <div className="startnode">Start<Handle type="source" position={Position.Right} id="next" /></div>;
}

const nodeTypes = { flow: FlowNode, start: StartNode };

function Canvas({ bot, detail, tools }: { bot: Bot; detail: FlowDetail; tools: Tool[] }) {
  const flowId = detail.flow.id;
  const rf = useReactFlow();
  const [nodes, setNodes] = useState<Node<NodeData>[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const riskySet = useMemo(() => new Set(tools.filter((t) => t.body.risky).map((t) => t.name)), [tools]);

  const persist = useCallback((ns: Node[], viewport?: unknown) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const positions: Record<string, { x: number; y: number }> = {};
      ns.forEach((n) => { if (n.id !== START_ID) positions[n.id] = { x: Math.round(n.position.x), y: Math.round(n.position.y) }; });
      const startPos = ns.find((n) => n.id === START_ID);
      void api.put(`/bots/${bot.slug}/flows/${flowId}/layout`, {
        viewport: viewport ?? rf.getViewport(), direction: "LR", nodes: positions,
        ...(startPos ? {} : {}),
      });
    }, 500);
  }, [bot.slug, flowId, rf]);

  const build = useCallback((auto: boolean) => {
    const g = detail.graph;
    const saved = detail.layout.nodes;
    const complete = g.nodes.every((n) => saved[n.id]);
    const placed = (auto || !complete) ? autoLayout(g.nodes, g.edges, g.start) : null;
    const pos = (id: string) => placed ? placed.find((p) => p.id === id)! : saved[id];
    const ns: Node<NodeData>[] = [
      { id: START_ID, type: "start", position: placed ? pos(START_ID) : { x: (pos(g.start)?.x ?? 0) - 110, y: (pos(g.start)?.y ?? 0) + 20 },
        data: {} as NodeData, draggable: true, selectable: false },
      ...g.nodes.map((n) => ({
        id: n.id, type: "flow", position: { x: pos(n.id).x, y: pos(n.id).y },
        data: { gn: n, risky: n.type === "call" && riskySet.has(n.data.tool), errors: detail.items.filter((i) => i.node_id === n.id),
                text: summary(n, riskySet) },
      })),
    ];
    setNodes(ns);
    if (placed) persist(ns);
    return ns;
  }, [detail, persist, riskySet]);

  useEffect(() => { build(false); setSelected(null); }, [build]);
  useEffect(() => {
    if (detail.layout.viewport) rf.setViewport(detail.layout.viewport);
    else window.setTimeout(() => rf.fitView({ padding: 0.1 }), 50);
  }, [flowId]); // eslint-disable-line react-hooks/exhaustive-deps

  const edges: Edge[] = useMemo(() => [
    { id: "start", source: START_ID, sourceHandle: "next", target: detail.graph.start, targetHandle: "in", type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed } },
    ...detail.graph.edges.map((e) => ({
      id: e.id, source: e.from, sourceHandle: e.handle, target: e.to, targetHandle: "in", type: "smoothstep",
      label: e.label || undefined, markerEnd: { type: MarkerType.ArrowClosed },
      style: e.handle === "error" || e.handle === "no" ? { stroke: "var(--err)" } : undefined,
      labelStyle: { fontSize: 10 }, labelBgStyle: { fillOpacity: 0.85 },
    })),
  ], [detail]);

  const sel = detail.graph.nodes.find((n) => n.id === selected);
  return (
    <div className="flowwrap">
      <div className="flowcanvas">
        <ReactFlow
          nodes={nodes.map((n) => ({ ...n, selected: n.id === selected }))} edges={edges} nodeTypes={nodeTypes}
          nodesConnectable={false} elementsSelectable
          onNodesChange={(ch) => setNodes((ns) => applyNodeChanges(ch, ns) as Node<NodeData>[])}
          onNodeClick={(_, n) => n.id !== START_ID && setSelected(n.id)} onPaneClick={() => setSelected(null)}
          onNodeDragStop={() => setNodes((ns) => { persist(ns); return ns; })}
          onMoveEnd={(_, vp) => persist(nodes, vp)}
          style={{ width: "100%", height: "100%" }} minZoom={0.2} fitView={!detail.layout.viewport}
        >
          <Background /><Controls showInteractive={false} /><MiniMap pannable zoomable />
        </ReactFlow>
      </div>
      <div className="flowside panel">
        <div className="row"><button onClick={() => { build(true); window.setTimeout(() => rf.fitView({ padding: 0.1 }), 50); }}>Auto layout</button>
          <button onClick={() => rf.fitView({ padding: 0.1 })}>Fit</button></div>
        <div className="legend">{KINDS.map((k) => <span key={k} className={`k-${k}`}>{k}</span>)}</div>
        <p className="small muted">Double border: the node waits for the caller. Lines: <code>yes/no</code>, <code>ok/error</code>, one per branch case, <code>else</code>.</p>
        {detail.items.length > 0 && <ul className="items">{detail.items.map((i, k) => (
          <li key={k} className={i.severity} onClick={() => i.node_id && setSelected(i.node_id)} style={{ cursor: i.node_id ? "pointer" : undefined }}>
            {i.node_id ? <b>node {i.node_id}: </b> : null}{i.message}</li>))}</ul>}
        {sel ? (
          <>
            <h4 style={{ margin: "8px 0 2px" }}>{sel.id} <span className="badge">{sel.type}</span></h4>
            <pre>{JSON.stringify(sel.data, null, 2)}</pre>
          </>
        ) : (
          <>
            <h4 style={{ margin: "8px 0 2px" }}>Flow {flowId}</h4>
            <pre>{JSON.stringify({ start: detail.flow.start, ...detail.flow.header }, null, 2)}</pre>
          </>
        )}
      </div>
    </div>
  );
}

export default function FlowView({ bot }: { bot: Bot }) {
  const { flowId } = useParams();
  const { data: detail, error } = useFetch<FlowDetail>(`/bots/${bot.slug}/flows/${flowId}`, [bot.draft_revision, bot.validated]);
  const { data: tools } = useFetch<Tool[]>(`/domains/${bot.domain}/tools`);
  return (
    <main>
      <p style={{ margin: "0 0 8px" }}><Link to={`/b/${bot.slug}/flows`}>← Flows</Link> / <b>{flowId}</b> <span className="muted small">read-only viewer</span></p>
      {error && <p style={{ color: "var(--err)" }}>{error.message}</p>}
      {detail && tools && <ReactFlowProvider><Canvas key={`${bot.slug}/${flowId}`} bot={bot} detail={detail} tools={tools} /></ReactFlowProvider>}
    </main>
  );
}
