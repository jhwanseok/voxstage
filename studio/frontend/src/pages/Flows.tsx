import { Link } from "react-router-dom";
import { type Bot, type FlowSummary } from "../api";
import { useFetch } from "../hooks";

function triggerText(t: any): string {
  if (!t) return "";
  return Object.entries(t).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join("  ");
}

export default function Flows({ bot }: { bot: Bot }) {
  const { data: flows } = useFetch<FlowSummary[]>(`/bots/${bot.slug}/flows`, [bot.draft_revision]);
  return (
    <main>
      <div className="panel">
        <table>
          <thead><tr><th>Flow</th><th>Triggers</th><th>Buttons</th><th>Nodes</th><th /></tr></thead>
          <tbody>
            {(flows ?? []).map((f) => (
              <tr key={f.id}>
                <td><Link to={`/b/${bot.slug}/flows/${f.id}`}>{f.id}</Link></td>
                <td className="small muted">{f.role ? "" : triggerText(f.triggers)}</td>
                <td className="small">{f.buttons.join(", ")}</td>
                <td>{f.node_count}</td>
                <td>
                  {f.role && <span className="badge warn">{f.role}</span>} {f.items.length > 0 && <span className="badge err">{f.items.length} problem{f.items.length > 1 ? "s" : ""}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">Flows of {bot.slug} are written in one language. Editing arrives in ST2; this screen is the viewer.</p>
      </div>
    </main>
  );
}
