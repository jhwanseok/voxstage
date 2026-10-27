import { useState } from "react";
import { Link } from "react-router-dom";
import { StatusBadge } from "../App";
import { ApiError, api, type Domain } from "../api";
import { useFetch, useShell } from "../hooks";

export default function Bots() {
  const { refresh, version } = useShell();
  const { data: domains, reload } = useFetch<Domain[]>("/domains", [version]);
  const { data: importable } = useFetch<string[]>("/domains/importable", [version]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const run = async (name: string, replace: boolean) => {
    setBusy(name); setMessage("");
    try {
      const s = await api.post<{ bots: { slug: string; modelled: string[]; raw: string[] }[] }>(
        "/domains/import", { domain: name, replace });
      setMessage(`Imported ${name}: ` + s.bots.map((b) => `${b.slug} (${b.modelled.length} modelled, ${b.raw.length} raw files)`).join(", "));
      refresh(); reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        if (window.confirm(`${name} already exists. Replace its draft with the files in domains/${name}? Publications are kept.`)) await run(name, true);
      } else setMessage((e as Error).message);
    } finally { setBusy(""); }
  };

  const present = new Set((domains ?? []).map((d) => d.slug));
  return (
    <main>
      <div className="topbar" style={{ margin: "-16px -16px 16px" }}>
        <span className="brand">voxstage studio</span>
        <span className="muted small">Domains and bots. A bot is one domain in one language.</span>
      </div>
      {message && <p className="panel small">{message}</p>}
      <div className="cards">
        {(domains ?? []).map((d) => (
          <div className="card" key={d.slug}>
            <h3>{d.slug}</h3>
            {d.bots.map((b) => (
              <div key={b.slug} className="row" style={{ margin: "6px 0" }}>
                <Link to={`/b/${b.slug}/faq`}>{b.slug}</Link>
                <span><StatusBadge bot={b} /> {b.has_unpublished_changes && <span className="badge warn">unpublished</span>} <span className="muted small">#{b.last_published_number || "–"}</span></span>
              </div>
            ))}
            <button className="small" disabled={busy === d.slug} onClick={() => run(d.slug, true)}
              title="Replace the draft with the files in domains/">Re-import draft</button>
          </div>
        ))}
        {(importable ?? []).filter((n) => !present.has(n)).map((n) => (
          <div className="card" key={n}>
            <h3>{n}</h3>
            <p className="muted small">In the repository's <code>domains/</code>, not imported yet.</p>
            <button className="primary" disabled={busy === n} onClick={() => run(n, false)}>{busy === n ? "Importing…" : "Import"}</button>
          </div>
        ))}
      </div>
    </main>
  );
}
