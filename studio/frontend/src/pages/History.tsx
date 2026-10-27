import { useState } from "react";
import { type Bot, type Publication } from "../api";
import { api } from "../api";
import { useFetch } from "../hooks";

interface PubDetail extends Publication { files: { path: string; size: number }[] }

export default function History({ bot }: { bot: Bot }) {
  const { data: pubs } = useFetch<Publication[]>(`/bots/${bot.slug}/publications`, [bot.last_published_number]);
  const [open, setOpen] = useState<PubDetail | null>(null);
  const [file, setFile] = useState<{ path: string; text: string } | null>(null);
  const show = async (n: number) => { setFile(null); setOpen(await api.get<PubDetail>(`/bots/${bot.slug}/publications/${n}`)); };
  const view = async (path: string) => {
    const res = await fetch(`/api/v1/bots/${bot.slug}/publications/${open!.number}/files/${path}`);
    setFile({ path, text: await res.text() });
  };
  return (
    <main>
      <div className="split">
        <div className="panel">
          <table>
            <thead><tr><th>#</th><th>Note</th><th>When</th><th /></tr></thead>
            <tbody>{(pubs ?? []).map((p) => (
              <tr key={p.number} className={"click" + (open?.number === p.number ? " sel" : "")} onClick={() => show(p.number)}>
                <td>{p.number}</td><td>{p.note || <span className="muted">(no note)</span>}</td>
                <td className="small muted">{new Date(p.published_at).toLocaleString()}</td>
                <td className="small">{p.file_count} files</td>
              </tr>))}</tbody>
          </table>
          {pubs && pubs.length === 0 && <p className="muted">Nothing published yet.</p>}
          <p className="small muted">Each publication is an immutable snapshot of the exported YAML. The newest one is in <code>studio/exports/{bot.slug}/</code>, which the engine can use as its domains directory. Diff and rollback arrive in ST2.</p>
        </div>
        <div className="panel">
          {open ? (
            <>
              <div className="row"><h4 style={{ margin: 0 }}>Publication {open.number}</h4>
                <a href={`/api/v1/bots/${bot.slug}/publications/${open.number}/export.zip`}>Download zip</a></div>
              <p className="small muted">hash {open.content_hash.slice(0, 12)}…</p>
              <table><tbody>{open.files.map((f) => (
                <tr key={f.path} className="click" onClick={() => view(f.path)}><td className="small">{f.path}</td><td className="small muted">{f.size} B</td></tr>))}</tbody></table>
              {file && <><h5>{file.path}</h5><pre>{file.text}</pre></>}
            </>
          ) : <span className="muted">Select a publication.</span>}
        </div>
      </div>
    </main>
  );
}
