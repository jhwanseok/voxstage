import { useEffect, useState } from "react";
import { ApiError, api, type Bot, type Tool } from "../api";
import { useFetch, useShell } from "../hooks";
import { fmt, parse, words } from "../lib/values";

type KV = [string, string][];
interface RuleDraft { when: KV; kind: "return" | "error"; ret: KV; error: string; delay: string }
interface Draft {
  name: string; params: string; risky: boolean; verifies: boolean; requires: string; retry: string;
  rules: RuleDraft[]; def: RuleDraft | null; revision: number | null;
}

const kv = (o: Record<string, unknown> | undefined): KV => Object.entries(o ?? {}).map(([k, v]) => [k, fmt(v)]);
const unkv = (rows: KV) => Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), parse(v)]));

function ruleToDraft(r: any): RuleDraft {
  return { when: kv(r.when), kind: "error" in r ? "error" : "return", ret: kv(r.return), error: r.error ?? "",
           delay: r.delay_ms === undefined ? "" : String(r.delay_ms) };
}
function draftToRule(r: RuleDraft, withWhen: boolean) {
  const o: any = {};
  if (withWhen) o.when = unkv(r.when);
  if (r.kind === "return") o.return = unkv(r.ret); else o.error = r.error;
  if (r.delay.trim() !== "") o.delay_ms = Number(r.delay);
  return o;
}

function toDraft(t: Tool | null): Draft {
  const b = t?.body ?? {};
  return {
    name: t?.name ?? "", params: (b.params ?? []).join(", "), risky: !!b.risky, verifies: !!b.verifies,
    requires: b.requires ?? "", retry: String(b.retry ?? 0), rules: (b.rules ?? []).map(ruleToDraft),
    def: b.default ? ruleToDraft(b.default) : null, revision: t?.revision ?? null,
  };
}

function toBody(d: Draft) {
  const b: any = { params: words(d.params) };
  if (d.requires) b.requires = d.requires;
  if (d.verifies) b.verifies = true;
  if (d.risky) b.risky = true;
  if (d.retry !== "0") b.retry = Number(d.retry);
  b.rules = d.rules.map((r) => draftToRule(r, true));
  if (d.def) b.default = draftToRule(d.def, false);
  return b;
}

function KVEditor({ rows, onChange, add }: { rows: KV; onChange: (r: KV) => void; add: string }) {
  return (
    <div>
      {rows.map(([k, v], i) => (
        <div className="row" key={i} style={{ marginBottom: 3 }}>
          <input value={k} placeholder="name" onChange={(e) => onChange(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} />
          <input value={v} placeholder="value" onChange={(e) => onChange(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} />
          <button onClick={() => onChange(rows.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button className="small" onClick={() => onChange([...rows, ["", ""]])}>{add}</button>
    </div>
  );
}

function RuleEditor({ r, onChange, withWhen }: { r: RuleDraft; onChange: (r: RuleDraft) => void; withWhen: boolean }) {
  return (
    <div className="card" style={{ marginBottom: 8, padding: 8 }}>
      {withWhen && <><label>when (parameter = value)</label><KVEditor rows={r.when} onChange={(when) => onChange({ ...r, when })} add="+ condition" /></>}
      <div className="row" style={{ marginTop: 6 }}>
        <select value={r.kind} onChange={(e) => onChange({ ...r, kind: e.target.value as "return" | "error" })}>
          <option value="return">return</option><option value="error">error</option>
        </select>
        <input value={r.delay} placeholder="delay_ms" onChange={(e) => onChange({ ...r, delay: e.target.value })} />
      </div>
      {r.kind === "return"
        ? <KVEditor rows={r.ret} onChange={(ret) => onChange({ ...r, ret })} add="+ field" />
        : <input value={r.error} placeholder="error code, e.g. timeout" onChange={(e) => onChange({ ...r, error: e.target.value })} />}
    </div>
  );
}

const empty = (): RuleDraft => ({ when: [], kind: "return", ret: [], error: "", delay: "" });

export default function ToolsPage({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data: tools, reload } = useFetch<Tool[]>(`/domains/${bot.domain}/tools`, [bot.shared_revision]);
  const [sel, setSel] = useState<string | "new" | null>(null);
  const [d, setD] = useState<Draft>(toDraft(null));
  const [msg, setMsg] = useState("");
  useEffect(() => { setSel(null); }, [bot.domain]);
  useEffect(() => {
    if (sel === "new") setD(toDraft(null)); else if (sel) setD(toDraft(tools?.find((t) => t.name === sel) ?? null));
    setMsg("");
  }, [sel, tools]);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  const save = async () => {
    try {
      const body = { name: d.name.trim(), body: toBody(d), revision: d.revision };
      const r: any = sel === "new" ? await api.post(`/domains/${bot.domain}/tools`, body)
                                   : await api.put(`/domains/${bot.domain}/tools/${sel}`, body);
      setMsg(`Saved. This changes the shared tools of ${bot.domain}: ${r.affects_bots.join(", ")} must be validated again.`);
      reload(); refresh(); if (sel === "new") setSel(body.name);
    } catch (e) { setMsg(e instanceof ApiError && e.status === 409 ? "Changed elsewhere; reload." : (e as Error).message); }
  };
  const remove = async () => {
    if (!sel || sel === "new") return;
    try {
      await api.del(`/domains/${bot.domain}/tools/${sel}`);
    } catch (e) {
      const flows = e instanceof ApiError ? e.body?.detail?.flows : null;
      if (flows && window.confirm(`Called by ${flows.map((f: any) => `${f.bot}/${f.flow}`).join(", ")}. Delete anyway?`)) {
        await api.del(`/domains/${bot.domain}/tools/${sel}?force=true`);
      } else return;
    }
    setSel(null); reload(); refresh();
  };

  return (
    <main>
      <p className="muted small">Tools are shared by every bot of the domain <b>{bot.domain}</b> (the fake backend API of the dataset).</p>
      <div className="split">
        <div className="panel">
          <div className="row"><span /><button className="primary" onClick={() => setSel("new")}>New tool</button></div>
          <table>
            <thead><tr><th>Name</th><th>Params</th><th /></tr></thead>
            <tbody>{(tools ?? []).map((t) => (
              <tr key={t.name} className={"click" + (sel === t.name ? " sel" : "")} onClick={() => setSel(t.name)}>
                <td>{t.name}</td><td className="small muted">{(t.body.params ?? []).join(", ")}</td>
                <td>{t.body.risky && <span className="badge err">risky</span>} {t.body.requires && <span className="badge warn">verified</span>} {t.body.verifies && <span className="badge ok">verifies</span>} {t.body.retry ? <span className="badge">retry</span> : null}</td>
              </tr>))}</tbody>
          </table>
        </div>
        {sel ? (
          <div className="panel">
            <label>Name</label><input value={d.name} disabled={sel !== "new"} onChange={(e) => set("name", e.target.value)} />
            <label>Params (comma separated)</label><input value={d.params} onChange={(e) => set("params", e.target.value)} />
            <div className="row" style={{ marginTop: 8 }}>
              <label className="fit"><input type="checkbox" style={{ width: "auto" }} checked={d.risky} onChange={(e) => set("risky", e.target.checked)} /> risky (a confirm must come first; no retry)</label>
              <label className="fit"><input type="checkbox" style={{ width: "auto" }} checked={d.verifies} onChange={(e) => set("verifies", e.target.checked)} /> verifies the caller</label>
            </div>
            <div className="row">
              <div><label>requires</label><select value={d.requires} onChange={(e) => set("requires", e.target.value)}><option value="">(nothing)</option><option value="verified">verified</option></select></div>
              <div><label>retry on timeout</label><select value={d.retry} onChange={(e) => set("retry", e.target.value)}><option value="0">0</option><option value="1">1</option></select></div>
            </div>
            <label>Fake API rules (first match wins)</label>
            {d.rules.map((r, i) => (
              <div key={i}>
                <RuleEditor r={r} withWhen onChange={(x) => set("rules", d.rules.map((y, j) => (j === i ? x : y)))} />
                <button className="small danger" onClick={() => set("rules", d.rules.filter((_, j) => j !== i))}>Remove rule {i + 1}</button>
              </div>
            ))}
            <button className="small" onClick={() => set("rules", [...d.rules, empty()])}>+ rule</button>
            <label>Default (when no rule matches)</label>
            {d.def ? <><RuleEditor r={d.def} withWhen={false} onChange={(x) => set("def", x)} /><button className="small" onClick={() => set("def", null)}>No default</button></>
                   : <button className="small" onClick={() => set("def", empty())}>+ default</button>}
            <div className="row" style={{ marginTop: 12 }}>
              <button className="primary" onClick={save}>Save</button>
              {sel !== "new" && <button className="danger" onClick={remove}>Delete</button>}
            </div>
            <p className="small muted">{msg}</p>
          </div>
        ) : <div className="panel muted">Select a tool.</div>}
      </div>
    </main>
  );
}
