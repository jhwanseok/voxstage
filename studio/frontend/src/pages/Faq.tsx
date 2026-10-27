import { useEffect, useState } from "react";
import { ApiError, api, type Bot, type Faq, type Pattern } from "../api";
import { useFetch, useShell } from "../hooks";
import { lines, words } from "../lib/values";

const MIN_PARAPHRASES = 3;
const MIN_ASR = 1;

interface Draft {
  id: string; question: string; answer: string; paraphrases: string; asr: string;
  all_of: string; any_of: string; none_of: string; priority: string; regex: string; hasPattern: boolean;
  revision: number | null;
}

function toDraft(e: Faq | null): Draft {
  const p = e?.pattern ?? {};
  return {
    id: e?.id ?? "", question: e?.question ?? "", answer: e?.answer ?? "",
    paraphrases: (e?.paraphrases ?? []).join("\n"), asr: (e?.asr_variants ?? []).join("\n"),
    all_of: (p.all_of ?? []).map((g) => (Array.isArray(g) ? g : [g]).join(", ")).join("\n"),
    any_of: (p.any_of ?? []).join(", "), none_of: (p.none_of ?? []).join(", "),
    priority: p.priority === undefined ? "" : String(p.priority), regex: (p.regex ?? []).join("\n"),
    hasPattern: !!e?.pattern, revision: e?.revision ?? null,
  };
}

function toPattern(d: Draft): Pattern | null {
  const p: Pattern = {};
  const groups = lines(d.all_of).map(words).filter((g) => g.length);
  if (groups.length) p.all_of = groups;
  if (words(d.any_of).length) p.any_of = words(d.any_of);
  if (words(d.none_of).length) p.none_of = words(d.none_of);
  if (d.priority.trim() !== "") p.priority = Number(d.priority);
  if (lines(d.regex).length) p.regex = lines(d.regex);
  return Object.keys(p).length ? p : d.hasPattern ? {} : null;
}

/** The pattern in plain words, as docs/studio/screens.md describes. */
export function readPattern(p: Pattern | null): string {
  if (!p) return "No pattern: the engine refuses a pack with a FAQ entry that has none.";
  const parts: string[] = [];
  (p.all_of ?? []).forEach((g) => parts.push(`one of [${(Array.isArray(g) ? g : [g]).join(", ")}]`));
  if (p.any_of?.length) parts.push(`at least one of [${p.any_of.join(", ")}]`);
  const need = parts.length ? "needs " + parts.join(" and ") : "";
  const not = p.none_of?.length ? `${need ? "; " : ""}none of [${p.none_of.join(", ")}]` : "";
  return (need + not) || "empty";
}

export default function FaqPage({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: list, reload } = useFetch<Faq[]>(`/bots/${bot.slug}/faq`);
  const { data: report } = useFetch<{ items: any[] } | null>(`/bots/${bot.slug}/validation`, [bot.draft_revision]);
  const [sel, setSel] = useState<string | "new" | null>(null);
  const [d, setD] = useState<Draft>(toDraft(null));
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => { setSel(null); }, [bot.slug]);
  useEffect(() => {
    if (sel === "new") setD(toDraft(null));
    else if (sel) setD(toDraft(list?.find((e) => e.id === sel) ?? null));
    setMsg("");
  }, [sel, list]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const items = (report?.items ?? []).filter((i) => /faq/.test(i.file));

  const save = async () => {
    const body = {
      id: d.id.trim(), question: d.question, answer: d.answer,
      paraphrases: lines(d.paraphrases), asr_variants: lines(d.asr), pattern: toPattern(d), revision: d.revision,
    };
    try {
      if (sel === "new") await api.post(`/bots/${bot.slug}/faq`, body); else await api.put(`/bots/${bot.slug}/faq/${sel}`, body);
      setMsg("Saved."); reload(); refresh();
      if (sel === "new") setSel(body.id);
    } catch (e) {
      setMsg(e instanceof ApiError && e.status === 409 ? "Someone changed this entry; reload it." : (e as Error).message);
    }
  };
  const remove = async () => {
    if (!sel || sel === "new" || !window.confirm(`Delete ${sel}?`)) return;
    await api.del(`/bots/${bot.slug}/faq/${sel}`); setSel(null); reload(); refresh();
  };

  const rows = (list ?? []).filter((e) => !q || (e.id + e.question).toLowerCase().includes(q.toLowerCase()));
  const nPara = lines(d.paraphrases).length, nAsr = lines(d.asr).length;
  return (
    <main>
      {items.length > 0 && <ul className="items">{items.map((i, k) => <li key={k}><b>{i.file}</b><br />{i.message}</li>)}</ul>}
      <div className="split">
        <div className="panel">
          <div className="row"><input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
            <button className="primary" onClick={() => setSel("new")}>New entry</button></div>
          <table>
            <thead><tr><th>Id</th><th>Question</th><th>Pattern</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} className={"click" + (sel === e.id ? " sel" : "")} onClick={() => setSel(e.id)}>
                  <td className="small">{e.id}</td><td>{e.question}</td>
                  <td className="small muted">{e.pattern ? "yes" : <span className="badge err">none</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sel ? (
          <div className="panel">
            <label>Id</label>
            <input value={d.id} disabled={sel !== "new"} onChange={(e) => set("id", e.target.value)} placeholder="bank.faq.hours" />
            <label>Question</label><input value={d.question} onChange={(e) => set("question", e.target.value)} />
            <label>Answer (spoken verbatim)</label><textarea value={d.answer} onChange={(e) => set("answer", e.target.value)} />
            <div className="row" style={{ alignItems: "flex-start" }}>
              <div>
                <label>Paraphrases, one per line <span className={nPara >= MIN_PARAPHRASES ? "" : "badge err"}>{nPara} / min {MIN_PARAPHRASES}</span></label>
                <textarea rows={6} value={d.paraphrases} onChange={(e) => set("paraphrases", e.target.value)} />
                <label>ASR variants, one per line <span className={nAsr >= MIN_ASR ? "" : "badge err"}>{nAsr} / min {MIN_ASR}</span></label>
                <textarea value={d.asr} onChange={(e) => set("asr", e.target.value)} />
              </div>
              <div>
                <label>Pattern: all_of groups, one group per line, words separated by commas</label>
                <textarea rows={3} value={d.all_of} onChange={(e) => set("all_of", e.target.value)} />
                <label>any_of (comma separated)</label><input value={d.any_of} onChange={(e) => set("any_of", e.target.value)} />
                <label>none_of (comma separated)</label><input value={d.none_of} onChange={(e) => set("none_of", e.target.value)} />
                <div className="row">
                  <div><label>priority</label><input value={d.priority} onChange={(e) => set("priority", e.target.value)} /></div>
                </div>
                <details><summary className="small muted">regex (only when word groups cannot say it)</summary>
                  <textarea value={d.regex} onChange={(e) => set("regex", e.target.value)} /></details>
                <p className="small muted">{readPattern(toPattern(d))}</p>
              </div>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <button className="primary" onClick={save}>Save</button>
              {sel !== "new" && <button className="danger" onClick={remove}>Delete</button>}
              <span className="muted small">{msg}</span>
            </div>
          </div>
        ) : <div className="panel muted">Select an entry. Paraphrases are shown next to the pattern; the studio does not enforce the held-out rule of the dataset.</div>}
      </div>
    </main>
  );
}
