import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Bot, type Report } from "../api";
import { useFetch, useShell } from "../hooks";

export default function Validation({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: report, reload } = useFetch<Report | null>(`/bots/${bot.slug}/validation`, [bot.validated, bot.draft_revision]);
  const [busy, setBusy] = useState(false);
  const run = async () => { setBusy(true); try { await api.post(`/bots/${bot.slug}/validate`); reload(); refresh(); } finally { setBusy(false); } };
  const stale = !bot.validated;
  return (
    <main>
      <div className="panel">
        <div className="row" style={{ marginBottom: 8 }}>
          <span>
            {!report ? "Not validated yet." : report.ok ? <span className="badge ok">the engine loads this bot</span> : <span className="badge err">{report.items.length} problem(s)</span>}
            {report && stale && <span className="badge warn" style={{ marginLeft: 8 }}>stale: the draft changed since</span>}
          </span>
          <button onClick={run} disabled={busy}>{busy ? "Validating…" : "Validate now"}</button>
        </div>
        <p className="small muted">This runs the engine's own loader on an export of the draft. The loader reports one problem per file at a time, so an empty list after fixing one problem is the answer, not a promise that nothing else will turn up in a file you have not fixed yet.</p>
        {report && report.items.length > 0 && (
          <table>
            <thead><tr><th>File</th><th>Where</th><th>Message</th></tr></thead>
            <tbody>{report.items.map((i, k) => (
              <tr key={k}>
                <td className="small">{i.file}</td>
                <td className="small">{i.flow_id ? <Link to={`/b/${bot.slug}/flows/${i.flow_id}`}>{i.flow_id}{i.node_id ? ` · ${i.node_id}` : ""}</Link> : ""}</td>
                <td>{i.message}</td>
              </tr>))}</tbody>
          </table>
        )}
      </div>
    </main>
  );
}
