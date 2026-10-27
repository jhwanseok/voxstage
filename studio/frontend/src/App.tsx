import { useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type Bot, type Publication, type Report } from "./api";
import { ShellContext, useFetch, useShell } from "./hooks";
import Bots from "./pages/Bots";
import Faq from "./pages/Faq";
import FlowView from "./pages/FlowView";
import Flows from "./pages/Flows";
import History from "./pages/History";
import Tools from "./pages/Tools";
import Validation from "./pages/Validation";

export function StatusBadge({ bot }: { bot: Bot }) {
  if (!bot.validated) return <span className="badge warn">not validated</span>;
  return bot.valid ? <span className="badge ok">valid</span> : <span className="badge err">has errors</span>;
}

function PublishDialog({ bot, onClose }: { bot: Bot; onClose: () => void }) {
  const { refresh } = useShell();
  const nav = useNavigate();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<Report | null>(null);
  const [message, setMessage] = useState("");
  const publish = async () => {
    setBusy(true); setMessage(""); setReport(null);
    try {
      const p = await api.post<Publication>(`/bots/${bot.slug}/publications`, { note });
      refresh(); onClose(); nav(`/b/${bot.slug}/history#${p.number}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) { setReport(e.body.report); refresh(); setMessage("The engine does not accept this draft; nothing was published."); }
      else setMessage((e as Error).message);
    } finally { setBusy(false); }
  };
  return (
    <div className="dialog-bg" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Publish {bot.slug}</h3>
        <p className="muted small">Validates the draft with the engine loader, stores an immutable snapshot (publication {bot.last_published_number + 1}) and writes <code>studio/exports/{bot.slug}/</code>.</p>
        <label>Note</label>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What changed" autoFocus />
        {message && <p style={{ color: "var(--err)" }}>{message}</p>}
        {report && <ul className="items">{report.items.map((i, k) => <li key={k} className={i.severity}><b>{i.file}</b>{i.node_id ? ` · node ${i.node_id}` : ""}<br />{i.message}</li>)}</ul>}
        <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={publish} disabled={busy}>{busy ? "Publishing…" : "Publish"}</button>
        </div>
      </div>
    </div>
  );
}

function BotShell() {
  const { bot: slug } = useParams();
  const { bots, refresh } = useShell();
  const nav = useNavigate();
  const [publishing, setPublishing] = useState(false);
  const [validating, setValidating] = useState(false);
  const bot = bots.find((b) => b.slug === slug);
  if (!bot) return <main>{bots.length ? "Unknown bot." : "Loading…"}</main>;
  const validate = async () => {
    setValidating(true);
    try { await api.post<Report>(`/bots/${bot.slug}/validate`); refresh(); nav(`/b/${bot.slug}/validation`); }
    finally { setValidating(false); }
  };
  return (
    <>
      <div className="topbar">
        <span className="brand"><NavLink to="/">voxstage studio</NavLink></span>
        <select value={bot.slug} onChange={(e) => nav(`/b/${e.target.value}/faq`)}>
          {bots.map((b) => <option key={b.slug} value={b.slug}>{b.slug}</option>)}
        </select>
        <StatusBadge bot={bot} />
        {bot.has_unpublished_changes && <span className="badge warn">unpublished changes</span>}
        <span className="muted small">published #{bot.last_published_number || "–"}</span>
        <span className="spacer" />
        <button onClick={validate} disabled={validating}>{validating ? "Validating…" : "Validate"}</button>
        <button className="primary" onClick={() => setPublishing(true)}>Publish</button>
      </div>
      <nav className="nav">
        {["faq", "tools", "flows", "validation", "history"].map((t) => (
          <NavLink key={t} to={`/b/${bot.slug}/${t}`} className={({ isActive }) => (isActive ? "active" : "")}>{t[0].toUpperCase() + t.slice(1)}</NavLink>
        ))}
      </nav>
      <Routes>
        <Route path="faq" element={<Faq bot={bot} />} />
        <Route path="tools" element={<Tools bot={bot} />} />
        <Route path="flows" element={<Flows bot={bot} />} />
        <Route path="flows/:flowId" element={<FlowView bot={bot} />} />
        <Route path="validation" element={<Validation bot={bot} />} />
        <Route path="history" element={<History bot={bot} />} />
        <Route path="*" element={<Navigate to="faq" replace />} />
      </Routes>
      {publishing && <PublishDialog bot={bot} onClose={() => setPublishing(false)} />}
    </>
  );
}

export default function App() {
  const [version, setVersion] = useState(0);
  const { data: bots } = useFetch<Bot[]>("/bots", [version]);
  const shell = { bots: bots ?? [], refresh: () => setVersion((v) => v + 1), version };
  return (
    <ShellContext.Provider value={shell}>
      <Routes>
        <Route path="/" element={<Bots />} />
        <Route path="/b/:bot/*" element={<BotShell />} />
      </Routes>
    </ShellContext.Provider>
  );
}
