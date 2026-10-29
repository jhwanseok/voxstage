import { Database, Plus, Trash2, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api, type Bot } from "../api";
import { domainName, EXTRACTORS } from "../copy";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import {
  fieldOut, fieldSpec, labelOf, NAME, TYPE_NAME, withLabel, type FieldSpec, type RoleDef, type TypeDef, type TypesDoc,
  type TypesResponse, type TypeUse, SESSION_ROLE,
} from "../lib/datatypes";
import {
  Button, Disclosure, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Segmented, Select,
  Sheet, StatusChip, eul, useToast, WordsInput,
} from "../ui";

const typeName = (t: string) => EXTRACTORS[t] ?? t;

function usageText(uses: TypeUse[] | undefined): string {
  if (!uses?.length) return "아직 쓰는 곳이 없어요";
  const flows = new Set(uses.filter((u) => u.scope === "flow").map((u) => `${u.bot}/${u.flow}`)).size;
  const session = uses.filter((u) => u.scope === "session").length;
  return [flows && `시나리오 ${flows}곳`, session && `통화 전체 속성 ${session}개`].filter(Boolean).join(", ") + "에서 써요";
}

/** Saves the whole dictionary; a removal that scenarios still use asks first (the server answers 409 with the uses). */
function useSaveDoc(bot: Bot, data: TypesResponse | null, onSaved: () => void) {
  const toast = useToast();
  return async (doc: TypesDoc): Promise<string | null> => {
    const send = (force: boolean) => api.put<TypesResponse>(`/domains/${bot.domain}/types`, { body: doc, revision: data?.revision ?? 0, force });
    try {
      await send(false);
    } catch (e) {
      if (!(e instanceof ApiError)) return (e as Error).message;
      if (e.status === 422) return (e.body?.detail?.problems ?? [e.message]).join(" ");
      const uses = e.body?.detail?.uses;
      if (e.status !== 409) return e.message;
      if (!uses) return "다른 곳에서 먼저 바뀌었어요. 닫고 다시 열어 주세요.";
      const where = uses.map((u: any) => `${u.flow}${u.node ? ` (${u.node})` : ""}`).join(", ");
      if (!window.confirm(`이 변경으로 시나리오에서 쓰던 속성이 사라져요: ${where}. 시나리오는 검증에서 고칠 곳으로 나와요. 그래도 저장할까요?`)) return "저장하지 않았어요";
      try { await send(true); } catch (e2) { return (e2 as Error).message; }
    }
    toast(`저장했어요. ${data?.affects_bots.length ?? 1}개 상담봇을 다시 검증해야 해요`);
    onSaved();
    return null;
  };
}

// --- one type ---

interface FieldRow { key: string; id: string; spec: FieldSpec }
interface TypeDraft { id: string; label: string; fields: FieldRow[] }

let rowKey = 0;
const nextKey = () => `f${++rowKey}`;

function toTypeDraft(id: string, t: TypeDef | null, lang: string): TypeDraft {
  return {
    id, label: t?.label?.[lang] ?? "",
    fields: Object.entries(t?.fields ?? {}).map(([fid, v]) => ({ key: nextKey(), id: fid, spec: fieldSpec(v) })),
  };
}
function toTypeDef(d: TypeDraft, prev: TypeDef | null, lang: string): TypeDef {
  const { fields: _f, label: _l, ...rest } = prev ?? { fields: {} };
  const base = withLabel({ ...rest, label: prev?.label, fields: {} } as TypeDef, lang, d.label);
  return { ...base, fields: Object.fromEntries(d.fields.map((f) => [f.id.trim(), fieldOut(f.spec)])) };
}

function FieldEditor({ row, lang, fieldTypes, onChange, onRemove, idError, index, focus }: {
  row: FieldRow; lang: string; fieldTypes: string[]; onChange: (r: FieldRow) => void; onRemove: () => void; idError: string | null; index: number;
  focus: boolean;
}) {
  const s = row.spec;
  const set = (patch: Partial<FieldSpec>) => onChange({ ...row, spec: { ...s, ...patch } });
  const types = fieldTypes.includes(s.type) ? fieldTypes : [...fieldTypes, s.type];
  const n = index + 1;
  return (
    <div className="space-y-3 rounded-lg border border-line p-3">
      <div className="grid grid-cols-[1fr_1fr_2rem] items-end gap-2">
        <Field label={`${n}. 표시 이름`}><Input autoFocus={focus} value={s.label?.[lang] ?? ""} placeholder={row.id || "예: 이름"} onChange={(e) => onChange({ ...row, spec: withLabel(s, lang, e.target.value) })} /></Field>
        <Field label="형식">
          <Select value={s.type} onChange={(e) => {
            const type = e.target.value;
            onChange({ ...row, spec: { ...s, type, length: type === "digits" ? s.length : undefined, choices: type === "choice" ? s.choices ?? [] : undefined } });
          }}>
            {types.map((t) => <option key={t} value={t}>{typeName(t)}</option>)}
          </Select>
        </Field>
        <IconButton label={`${n}번째 항목 지우기`} onClick={onRemove}><Trash2 size={14} /></IconButton>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="이름" hint="파일과 시나리오에서 가리켜요." error={idError}>
          <Input className="font-mono text-[13px]" value={row.id} onChange={(e) => onChange({ ...row, id: e.target.value })} />
        </Field>
        {s.type === "digits" && (
          <Field label="자릿수" optional hint="비우면 따지지 않아요.">
            <Input type="number" min={1} className="num" value={s.length ?? ""} onChange={(e) => set({ length: e.target.value === "" ? undefined : Number(e.target.value) })} />
          </Field>
        )}
      </div>
      {s.type === "choice" && (Array.isArray(s.choices) || !s.choices ? (
        <Field label="보기" hint="고객이 말하는 단어 그대로 저장해요." error={(s.choices as string[] | undefined)?.length ? null : "보기를 하나 이상 넣어 주세요"}>
          <WordsInput label={`${n}번째 항목 보기`} value={((s.choices ?? []) as string[]).map(String)} onChange={(choices) => set({ choices })} placeholder="보기 입력 후 Enter" />
        </Field>
      ) : (
        <div className="text-[13px]">
          <div className="mb-1 font-medium text-ink">보기 (고객이 하는 말과 저장할 값)</div>
          <ul className="space-y-0.5 text-ink-2">{Object.entries(s.choices).map(([w, v]) => <li key={w}>{w} <span className="text-muted">→</span> <code>{String(v)}</code></li>)}</ul>
          <p className="mt-1 text-xs text-muted">말과 값이 다른 보기는 여기서 고칠 수 없어요. 저장해도 그대로 남아요.</p>
        </div>
      ))}
    </div>
  );
}

function TypeEditor({ bot, doc, id, uses, fieldTypes, onClose, save }: {
  bot: Bot; doc: TypesDoc; id: string | null; uses: TypeUse[]; fieldTypes: string[]; onClose: () => void; save: (doc: TypesDoc) => Promise<string | null>;
}) {
  const prev = id ? doc.types[id] : null;
  const fresh = useMemo(() => toTypeDraft(id ?? "", prev, bot.lang), [id, prev, bot.lang]);
  const [d, setD] = useState(fresh);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [added, setAdded] = useState<string | null>(null);   // the field just added takes the focus
  const dirty = JSON.stringify(d) !== JSON.stringify(fresh);
  useUnsavedWarning(dirty);
  const isNew = id === null;
  const close = () => { if (!dirty || window.confirm("저장하지 않은 변경이 있어요. 버리고 닫을까요?")) onClose(); };

  const idErr = !d.id ? null : !TYPE_NAME.test(d.id) ? "영문 대문자로 시작하고 영문과 숫자만 써 주세요 (예: Person)"
    : isNew && doc.types[d.id] ? "이미 있는 이름이에요" : null;
  const fieldErr = (r: FieldRow) => !r.id ? "이름을 넣어 주세요" : !NAME.test(r.id) ? "영문 소문자, 숫자, 밑줄만 써 주세요"
    : d.fields.filter((x) => x.id === r.id).length > 1 ? "이름이 겹쳐요" : null;
  const blocking = !d.id || !!idErr || !d.fields.length || d.fields.some((f) => fieldErr(f) || (f.spec.type === "choice" && !Object.keys(f.spec.choices ?? {}).length));

  const submit = async (next: TypesDoc) => {
    setBusy(true); setErr("");
    const e = await save(next);
    setBusy(false);
    if (e) setErr(e);
  };
  const onSave = () => submit({ ...doc, types: { ...doc.types, [d.id]: toTypeDef(d, prev, bot.lang) } });
  const onDelete = () => {
    if (!id || !window.confirm(`${eul(labelOf(prev ?? undefined, id, bot.lang))} 지울까요?`)) return;
    const { [id]: _gone, ...types } = doc.types;
    void submit({ ...doc, types });
  };
  const addField = () => {
    let n = d.fields.length + 1;
    while (d.fields.some((f) => f.id === `field_${n}`)) n += 1;
    const key = nextKey();
    setAdded(key);
    setD({ ...d, fields: [...d.fields, { key, id: `field_${n}`, spec: { type: "text" } }] });
  };

  return (
    <Sheet open onClose={close} subtitle={isNew ? "새 속성 종류" : "속성 종류 수정"} title={d.label || d.id || "새 속성 종류"}
      footer={<>
        {!isNew && <Button variant="danger" icon={<Trash2 size={15} />} disabled={uses.length > 0} onClick={onDelete}
          title={uses.length ? "쓰는 곳이 있어 지울 수 없어요" : undefined}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status">{err ? <span className="font-medium text-err-fg">{err}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}</span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || blocking} onClick={onSave}>저장</Button>
      </>}>
      <div className="space-y-6">
        <Notice tone="brand" title={`${domainName(bot.domain)}의 모든 상담봇이 함께 써요`}>
          {uses.length ? `${usageText(uses)}. 항목을 지우면 그 항목을 묻거나 넘기던 단계를 고쳐야 해요.` : "고객에게서 수집하는 속성의 모양을 정해요. 시나리오에서 예약자, 방문자처럼 이름을 붙여 써요."}
        </Notice>
        <Field label="표시 이름" hint="화면과 고객에게 다시 읽어 줄 때 써요.">
          <Input data-autofocus={isNew || undefined} value={d.label} placeholder="예: 사람" onChange={(e) => setD({ ...d, label: e.target.value })} />
        </Field>
        <div className="space-y-3">
          <div>
            <div className="text-sm font-medium text-ink">항목</div>
            <p className="mt-0.5 text-xs text-muted">사람처럼 여러 항목을 함께 가지는 종류예요. 항목에는 하나의 값만 들어가고, 다른 종류를 넣을 수는 없어요.</p>
          </div>
          {d.fields.length === 0 && <p className="text-[13px] text-muted">항목을 하나 이상 넣어 주세요.</p>}
          {d.fields.map((f, i) => (
            <FieldEditor key={f.key} index={i} row={f} focus={f.key === added} lang={bot.lang} fieldTypes={fieldTypes} idError={fieldErr(f)}
              onChange={(r) => setD({ ...d, fields: d.fields.map((x) => (x.key === f.key ? r : x)) })}
              onRemove={() => setD({ ...d, fields: d.fields.filter((x) => x.key !== f.key) })} />
          ))}
          <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={addField}>항목 추가</Button>
        </div>
        <Disclosure title="개발 정보" summary={d.id || "이름 없음"} defaultOpen={isNew}>
          <Field label="이름" hint={isNew ? "파일과 시나리오에서 이 종류를 가리켜요. 만든 뒤에는 바꿀 수 없어요." : "만든 뒤에는 바꿀 수 없어요."} error={idErr}>
            <Input className="font-mono text-[13px]" value={d.id} disabled={!isNew} placeholder="Person" onChange={(e) => setD({ ...d, id: e.target.value })} />
          </Field>
        </Disclosure>
      </div>
    </Sheet>
  );
}

// --- the caller (the one session role, filled by the identity check) ---

function CallerEditor({ bot, doc, onClose, save }: {
  bot: Bot; doc: TypesDoc; onClose: () => void; save: (doc: TypesDoc) => Promise<string | null>;
}) {
  const prev = doc.session_roles[SESSION_ROLE] ?? null;
  const records = Object.entries(doc.types);
  const fresh = useMemo(() => ({ label: prev?.label?.[bot.lang] ?? "", type: prev?.type ?? records[0]?.[0] ?? "" }), [prev, bot.lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState(fresh);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dirty = JSON.stringify(d) !== JSON.stringify(fresh) || !prev;
  useUnsavedWarning(dirty && !!prev);
  const close = () => { if (!prev || JSON.stringify(d) === JSON.stringify(fresh) || window.confirm("저장하지 않은 변경이 있어요. 버리고 닫을까요?")) onClose(); };

  const submit = async (next: TypesDoc) => {
    setBusy(true); setErr("");
    const e = await save(next);
    setBusy(false);
    if (e) setErr(e);
  };
  const onSave = () => {
    const role: RoleDef = withLabel({ ...(prev ?? {}), type: d.type } as RoleDef, bot.lang, d.label);
    void submit({ ...doc, session_roles: { ...doc.session_roles, [SESSION_ROLE]: role } });
  };
  const onDelete = () => {
    if (!prev || !window.confirm(`${eul(labelOf(prev, SESSION_ROLE, bot.lang))} 지울까요? 이 속성을 넘기던 단계는 고쳐야 해요.`)) return;
    const { [SESSION_ROLE]: _gone, ...session_roles } = doc.session_roles;
    void submit({ ...doc, session_roles });
  };

  return (
    <Sheet open onClose={close} subtitle="통화 전체 속성" title={d.label || "발신자"} width={480}
      footer={<>
        {prev && <Button variant="danger" icon={<Trash2 size={15} />} onClick={onDelete}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status">{err ? <span className="font-medium text-err-fg">{err}</span> : dirty && prev ? <span className="text-warn-fg">저장하지 않음</span> : null}</span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || !d.type} onClick={onSave}>저장</Button>
      </>}>
      <div className="space-y-6">
        <p className="text-[13px] text-ink-2">전화를 건 고객이에요. 본인 확인을 마치면 확인에 쓴 값이 이 속성의 항목에 들어가고, 통화가 끝날 때까지 모든 시나리오에서 다시 묻지 않고 써요.</p>
        <Field label="표시 이름"><Input data-autofocus value={d.label} placeholder="예: 발신자" onChange={(e) => setD({ ...d, label: e.target.value })} /></Field>
        <Field label="속성 종류" hint="본인 확인에 쓰는 값과 같은 이름의 항목이 채워져요.">
          <Select value={d.type} onChange={(e) => setD({ ...d, type: e.target.value })}>
            {records.map(([tid, t]) => <option key={tid} value={tid}>{labelOf(t, tid, bot.lang)}</option>)}
          </Select>
        </Field>
      </div>
    </Sheet>
  );
}

// --- the page ---

export default function DataPage({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data, error, loading, reload } = useFetch<TypesResponse>(`/domains/${bot.domain}/types`, [bot.shared_revision]);
  const [open, setOpen] = useState<{ kind: "type" | "caller"; id: string | null } | null>(null);
  const save = useSaveDoc(bot, data, () => { reload(); refresh(); setOpen(null); });
  const doc: TypesDoc = { types: {}, session_roles: {}, ...data?.body };
  const types = Object.entries(doc.types);
  const caller = doc.session_roles[SESSION_ROLE];
  const fieldTypes = data?.field_types ?? Object.keys(EXTRACTORS);

  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="데이터" description={`상담봇이 고객에게서 수집하는 속성의 모양이에요. ${domainName(bot.domain)}의 모든 상담봇이 함께 써요.`}
        actions={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setOpen({ kind: "type", id: null })}>속성 종류 추가</Button>} />
      {error && <ErrorState error={error} onRetry={reload} what="데이터" />}
      {loading && <LoadingBlock rows={4} />}
      {data && (
        <div className="space-y-10">
          <section aria-labelledby="types-h">
            <h2 id="types-h" className="mb-3 text-[15px] font-semibold text-ink">속성 종류 <span className="num ml-1 text-muted">{types.length}</span></h2>
            {types.length === 0 ? (
              <EmptyState icon={<Database size={20} />} title="아직 속성 종류가 없어요" action={<Button variant="primary" onClick={() => setOpen({ kind: "type", id: null })}>속성 종류 추가</Button>}>
                예약자와 방문자처럼 같은 모양의 속성이 한 시나리오에 두 번 나온다면, 먼저 '사람' 같은 종류를 만들어 보세요.
              </EmptyState>
            ) : (
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
                {types.map(([tid, t]) => {
                  const fields = Object.entries(t.fields ?? {});
                  const uses = data.usage[tid] ?? [];
                  return (
                    <li key={tid}>
                      <button type="button" onClick={() => setOpen({ kind: "type", id: tid })} className="flex w-full items-center gap-4 px-5 py-3.5 text-left hover:bg-sunken/60">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold text-ink">{labelOf(t, tid, bot.lang)}</div>
                          <div className="mt-0.5 truncate text-xs text-muted">
                            항목 {fields.length}개: {fields.map(([f, v]) => labelOf(fieldSpec(v), f, bot.lang)).join(", ")}
                          </div>
                        </div>
                        <StatusChip tone={uses.length ? "brand" : "idle"} icon={false}>{usageText(uses)}</StatusChip>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section aria-labelledby="roles-h">
            <h2 id="roles-h" className="text-[15px] font-semibold text-ink">통화 전체에서 쓰는 속성</h2>
            <p className="mb-3 mt-0.5 text-xs text-muted">본인 확인을 마친 발신자는 통화가 끝날 때까지 모든 시나리오에서 써요. 한 시나리오 안에서만 쓰는 속성은 시나리오 설정에서 정해요.</p>
            {caller ? (
              <button type="button" onClick={() => setOpen({ kind: "caller", id: SESSION_ROLE })} className="flex w-full items-center gap-4 rounded-xl border border-line bg-surface px-5 py-3.5 text-left hover:bg-sunken/60">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700"><UserRound size={15} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-ink">{labelOf(caller, SESSION_ROLE, bot.lang)}</div>
                  <div className="mt-0.5 truncate text-xs text-muted">{labelOf(doc.types[caller.type], caller.type, bot.lang)}, 본인 확인이 채워요</div>
                </div>
              </button>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-line-strong/50 bg-surface px-5 py-4 text-[13px] text-muted">
                {types.length ? "아직 정하지 않았어요. 본인 확인한 발신자의 속성을 여러 시나리오에서 쓰려면 정해 주세요." : "속성 종류를 먼저 만들면 정할 수 있어요."}
                <Button size="sm" icon={<Plus size={14} />} disabled={!types.length} onClick={() => setOpen({ kind: "caller", id: null })}>발신자 정하기</Button>
              </div>
            )}
          </section>
        </div>
      )}
      {data && open?.kind === "type" && <TypeEditor key={open.id ?? "new"} bot={bot} doc={doc} id={open.id} uses={open.id ? data.usage[open.id] ?? [] : []}
        fieldTypes={fieldTypes} onClose={() => setOpen(null)} save={save} />}
      {data && open?.kind === "caller" && <CallerEditor bot={bot} doc={doc} onClose={() => setOpen(null)} save={save} />}
    </main>
  );
}
