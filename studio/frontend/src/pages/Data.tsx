import { Database, Plus, Trash2, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiError, api, type Bot } from "../api";
import { domainName, EXTRACTORS } from "../copy";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import {
  fieldOut, fieldSpec, labelOf, NAME, TYPE_NAME, withLabel, type FieldSpec, type RoleDef, type TypeDef, type TypesDoc,
  type TypesResponse, type TypeUse,
} from "../lib/datatypes";
import {
  Button, Disclosure, EmptyState, ErrorState, Field, IconButton, Input, LoadingBlock, Notice, PageHeader, Segmented, Select,
  Sheet, StatusChip, eul, useToast, WordsInput,
} from "../ui";

const typeName = (t: string) => EXTRACTORS[t] ?? t;
const LENGTH_KINDS = new Set(["digits", "text"]);

function usageText(uses: TypeUse[] | undefined): string {
  if (!uses?.length) return "아직 쓰는 곳이 없어요";
  const flows = new Set(uses.filter((u) => u.scope === "flow").map((u) => `${u.bot}/${u.flow}`)).size;
  const session = uses.filter((u) => u.scope === "session").length;
  return [flows && `시나리오 ${flows}곳`, session && `통화 전체 값 ${session}개`].filter(Boolean).join(", ") + "에서 써요";
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
      if (!window.confirm(`이 변경으로 시나리오에서 쓰던 값이 사라져요: ${where}. 시나리오는 검증에서 고칠 곳으로 나와요. 그래도 저장할까요?`)) return "저장하지 않았어요";
      try { await send(true); } catch (e2) { return (e2 as Error).message; }
    }
    toast(`저장했어요. ${data?.affects_bots.length ?? 1}개 상담봇을 다시 검증해야 해요`);
    onSaved();
    return null;
  };
}

// --- one type ---

interface FieldRow { key: string; id: string; spec: FieldSpec }
interface TypeDraft { id: string; label: string; shape: "fields" | "scalar"; fields: FieldRow[]; scalar: string }

let rowKey = 0;
const nextKey = () => `f${++rowKey}`;

function toTypeDraft(id: string, t: TypeDef | null, lang: string): TypeDraft {
  return {
    id, label: t?.label?.[lang] ?? "", shape: t && "scalar" in t ? "scalar" : "fields", scalar: t?.scalar ?? "number",
    fields: Object.entries(t?.fields ?? {}).map(([fid, v]) => ({ key: nextKey(), id: fid, spec: fieldSpec(v) })),
  };
}
function toTypeDef(d: TypeDraft, prev: TypeDef | null, lang: string): TypeDef {
  const { fields: _f, scalar: _s, label: _l, ...rest } = prev ?? {};
  const base = withLabel({ ...rest, label: prev?.label } as TypeDef, lang, d.label);
  return d.shape === "scalar" ? { ...base, scalar: d.scalar }
    : { ...base, fields: Object.fromEntries(d.fields.map((f) => [f.id.trim(), fieldOut(f.spec)])) };
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
            onChange({ ...row, spec: { ...s, type, length: LENGTH_KINDS.has(type) ? s.length : undefined, values: type === "choice" ? s.values ?? [] : undefined } });
          }}>
            {types.map((t) => <option key={t} value={t}>{typeName(t)}</option>)}
          </Select>
        </Field>
        <IconButton label={`${n}번째 필드 지우기`} onClick={onRemove}><Trash2 size={14} /></IconButton>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="이름" hint="파일과 시나리오에서 가리켜요." error={idError}>
          <Input className="font-mono text-[13px]" value={row.id} onChange={(e) => onChange({ ...row, id: e.target.value })} />
        </Field>
        {(s.type === "digits" || (LENGTH_KINDS.has(s.type) && s.length != null)) && (
          <Field label="자릿수" optional hint="비우면 따지지 않아요.">
            <Input type="number" min={1} className="num" value={s.length ?? ""} onChange={(e) => set({ length: e.target.value === "" ? undefined : Number(e.target.value) })} />
          </Field>
        )}
      </div>
      {s.type === "choice" && (
        <Field label="보기" error={(s.values ?? []).length ? null : "보기를 하나 이상 넣어 주세요"}>
          <WordsInput label={`${n}번째 필드 보기`} value={(s.values ?? []).map(String)} onChange={(values) => set({ values })} placeholder="저장할 값 입력 후 Enter" />
        </Field>
      )}
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
  const blocking = !d.id || !!idErr || (d.shape === "fields" && (!d.fields.length || d.fields.some((f) => fieldErr(f) || (f.spec.type === "choice" && !(f.spec.values ?? []).length))));

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
    <Sheet open onClose={close} subtitle={isNew ? "새 값의 종류" : "값의 종류 수정"} title={d.label || d.id || "새 값의 종류"}
      footer={<>
        {!isNew && <Button variant="danger" icon={<Trash2 size={15} />} disabled={uses.length > 0} onClick={onDelete}
          title={uses.length ? "쓰는 곳이 있어 지울 수 없어요" : undefined}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status">{err ? <span className="font-medium text-err-fg">{err}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}</span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || blocking} onClick={onSave}>저장</Button>
      </>}>
      <div className="space-y-6">
        <Notice tone="brand" title={`${domainName(bot.domain)}의 모든 상담봇이 함께 써요`}>
          {uses.length ? `${usageText(uses)}. 필드를 지우면 그 필드를 묻거나 넘기던 단계를 고쳐야 해요.` : "고객에게서 받는 값의 모양을 정해요. 시나리오에서 예약자, 방문자처럼 이름을 붙여 써요."}
        </Notice>
        <Field label="표시 이름" hint="화면과 고객에게 다시 읽어 줄 때 써요.">
          <Input data-autofocus={isNew || undefined} value={d.label} placeholder="예: 사람" onChange={(e) => setD({ ...d, label: e.target.value })} />
        </Field>
        <div>
          <div className="mb-1.5 text-sm font-medium text-ink">모양</div>
          <Segmented label="모양" value={d.shape} onChange={(shape) => setD({ ...d, shape })}
            options={[{ value: "fields", label: "여러 값의 묶음" }, { value: "scalar", label: "값 하나" }]} />
          <p className="mt-1.5 text-xs text-muted">{d.shape === "fields" ? "사람처럼 이름, 전화번호를 함께 가지는 값이에요. 필드 안에 다른 묶음은 넣을 수 없어요." : "금액처럼 하나의 값이에요."}</p>
        </div>
        {d.shape === "fields" ? (
          <div className="space-y-3">
            <div className="text-sm font-medium text-ink">필드</div>
            {d.fields.length === 0 && <p className="text-[13px] text-muted">필드를 하나 이상 넣어 주세요.</p>}
            {d.fields.map((f, i) => (
              <FieldEditor key={f.key} index={i} row={f} focus={f.key === added} lang={bot.lang} fieldTypes={fieldTypes} idError={fieldErr(f)}
                onChange={(r) => setD({ ...d, fields: d.fields.map((x) => (x.key === f.key ? r : x)) })}
                onRemove={() => setD({ ...d, fields: d.fields.filter((x) => x.key !== f.key) })} />
            ))}
            <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={addField}>필드 추가</Button>
          </div>
        ) : (
          <Field label="형식">
            <Select value={d.scalar} onChange={(e) => setD({ ...d, scalar: e.target.value })}>
              {(fieldTypes.includes(d.scalar) ? fieldTypes : [...fieldTypes, d.scalar]).map((t) => <option key={t} value={t}>{typeName(t)}</option>)}
            </Select>
          </Field>
        )}
        <Disclosure title="개발 정보" summary={d.id || "이름 없음"} defaultOpen={isNew}>
          <Field label="이름" hint={isNew ? "파일과 시나리오에서 이 종류를 가리켜요. 만든 뒤에는 바꿀 수 없어요." : "만든 뒤에는 바꿀 수 없어요."} error={idErr}>
            <Input className="font-mono text-[13px]" value={d.id} disabled={!isNew} placeholder="Person" onChange={(e) => setD({ ...d, id: e.target.value })} />
          </Field>
        </Disclosure>
      </div>
    </Sheet>
  );
}

// --- one call-wide value (session role) ---

function SessionRoleEditor({ bot, doc, id, onClose, save }: {
  bot: Bot; doc: TypesDoc; id: string | null; onClose: () => void; save: (doc: TypesDoc) => Promise<string | null>;
}) {
  const prev = id ? doc.roles[id] : null;
  const records = Object.entries(doc.types).filter(([, t]) => t.fields);
  const fresh = useMemo(() => ({ id: id ?? "", label: prev?.label?.[bot.lang] ?? "", type: prev?.type ?? records[0]?.[0] ?? "" }), [id, prev, bot.lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState(fresh);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dirty = JSON.stringify(d) !== JSON.stringify(fresh);
  useUnsavedWarning(dirty);
  const isNew = id === null;
  const close = () => { if (!dirty || window.confirm("저장하지 않은 변경이 있어요. 버리고 닫을까요?")) onClose(); };
  const idErr = !d.id ? null : !NAME.test(d.id) ? "영문 소문자, 숫자, 밑줄만 써 주세요 (예: caller)" : isNew && doc.roles[d.id] ? "이미 있는 이름이에요" : null;

  const submit = async (next: TypesDoc) => {
    setBusy(true); setErr("");
    const e = await save(next);
    setBusy(false);
    if (e) setErr(e);
  };
  const onSave = () => {
    const role: RoleDef = withLabel({ ...(prev ?? {}), type: d.type, scope: "session" } as RoleDef, bot.lang, d.label);
    void submit({ ...doc, roles: { ...doc.roles, [d.id]: role } });
  };
  const onDelete = () => {
    if (!id || !window.confirm(`${eul(labelOf(prev ?? undefined, id, bot.lang))} 지울까요?`)) return;
    const { [id]: _gone, ...roles } = doc.roles;
    void submit({ ...doc, roles });
  };

  return (
    <Sheet open onClose={close} subtitle={isNew ? "새 통화 전체 값" : "통화 전체 값 수정"} title={d.label || d.id || "새 통화 전체 값"} width={480}
      footer={<>
        {!isNew && <Button variant="danger" icon={<Trash2 size={15} />} onClick={onDelete}>삭제</Button>}
        <span className="flex-1 truncate text-right text-[13px]" role="status">{err ? <span className="font-medium text-err-fg">{err}</span> : dirty ? <span className="text-warn-fg">저장하지 않음</span> : null}</span>
        <Button onClick={close}>취소</Button>
        <Button variant="primary" loading={busy} disabled={!dirty || !d.id || !!idErr || !d.type} onClick={onSave}>저장</Button>
      </>}>
      <div className="space-y-6">
        <p className="text-[13px] text-ink-2">통화가 끝날 때까지 모든 시나리오에서 같은 값을 써요. 본인 확인을 마친 고객처럼, 한 번 받으면 다시 묻지 않아요.</p>
        <Field label="표시 이름"><Input data-autofocus={isNew || undefined} value={d.label} placeholder="예: 전화 건 사람" onChange={(e) => setD({ ...d, label: e.target.value })} /></Field>
        <Field label="값의 종류" error={records.length ? null : "먼저 여러 값의 묶음인 값의 종류를 만들어 주세요"}>
          <Select value={d.type} onChange={(e) => setD({ ...d, type: e.target.value })}>
            {records.map(([tid, t]) => <option key={tid} value={tid}>{labelOf(t, tid, bot.lang)}</option>)}
          </Select>
        </Field>
        {prev?.filled_by && <Notice tone="idle" title="채우는 곳">{`본인 확인(${prev.filled_by})이 이 값을 채워요. 이 설정은 파일에서 읽은 그대로 둬요.`}</Notice>}
        <Disclosure title="개발 정보" summary={d.id || "이름 없음"} defaultOpen={isNew}>
          <Field label="이름" hint="만든 뒤에는 바꿀 수 없어요." error={idErr}>
            <Input className="font-mono text-[13px]" value={d.id} disabled={!isNew} placeholder="caller" onChange={(e) => setD({ ...d, id: e.target.value })} />
          </Field>
        </Disclosure>
      </div>
    </Sheet>
  );
}

// --- the page ---

export default function DataPage({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const { data, error, loading, reload } = useFetch<TypesResponse>(`/domains/${bot.domain}/types`, [bot.shared_revision]);
  const [open, setOpen] = useState<{ kind: "type" | "role"; id: string | null } | null>(null);
  const save = useSaveDoc(bot, data, () => { reload(); refresh(); setOpen(null); });
  const doc = data?.body ?? { types: {}, roles: {} };
  const types = Object.entries(doc.types);
  const roles = Object.entries(doc.roles);
  const fieldTypes = data?.field_types ?? Object.keys(EXTRACTORS);

  return (
    <main className="mx-auto max-w-5xl px-8 py-8">
      <PageHeader title="데이터" description={`상담봇이 고객에게서 받는 값의 모양이에요. ${domainName(bot.domain)}의 모든 상담봇이 함께 써요.`}
        actions={<Button variant="primary" icon={<Plus size={15} />} onClick={() => setOpen({ kind: "type", id: null })}>값의 종류 추가</Button>} />
      {error && <ErrorState error={error} onRetry={reload} what="데이터" />}
      {loading && <LoadingBlock rows={4} />}
      {data && (
        <div className="space-y-10">
          <section aria-labelledby="types-h">
            <h2 id="types-h" className="mb-3 text-[15px] font-semibold text-ink">값의 종류 <span className="num ml-1 text-muted">{types.length}</span></h2>
            {types.length === 0 ? (
              <EmptyState icon={<Database size={20} />} title="아직 값의 종류가 없어요" action={<Button variant="primary" onClick={() => setOpen({ kind: "type", id: null })}>값의 종류 추가</Button>}>
                예약자와 방문자처럼 같은 모양의 값이 한 시나리오에 두 번 나온다면, 먼저 '사람' 같은 종류를 만들어 보세요.
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
                            {t.fields ? `필드 ${fields.length}개: ${fields.map(([f, v]) => labelOf(fieldSpec(v), f, bot.lang)).join(", ")}` : `값 하나, ${typeName(t.scalar ?? "")}`}
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
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 id="roles-h" className="text-[15px] font-semibold text-ink">통화 전체에서 쓰는 값 <span className="num ml-1 text-muted">{roles.length}</span></h2>
                <p className="mt-0.5 text-xs text-muted">통화가 끝날 때까지 모든 시나리오에서 써요. 한 시나리오 안에서만 쓰는 값은 시나리오 설정에서 정해요.</p>
              </div>
              <Button size="sm" icon={<Plus size={14} />} disabled={!types.some(([, t]) => t.fields)} onClick={() => setOpen({ kind: "role", id: null })}>추가</Button>
            </div>
            {roles.length === 0 ? (
              <p className="rounded-xl border border-dashed border-line-strong/50 bg-surface px-5 py-6 text-center text-[13px] text-muted">
                {types.some(([, t]) => t.fields) ? "아직 없어요. 본인 확인을 마친 고객처럼 여러 시나리오가 함께 쓰는 값을 넣어 보세요." : "값의 종류를 먼저 만들면 넣을 수 있어요."}
              </p>
            ) : (
              <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
                {roles.map(([rid, r]) => (
                  <li key={rid}>
                    <button type="button" onClick={() => setOpen({ kind: "role", id: rid })} className="flex w-full items-center gap-4 px-5 py-3.5 text-left hover:bg-sunken/60">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700"><UserRound size={15} aria-hidden /></span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-ink">{labelOf(r, rid, bot.lang)}</div>
                        <div className="mt-0.5 truncate text-xs text-muted">{labelOf(doc.types[r.type], r.type, bot.lang)}{r.filled_by ? ", 본인 확인이 채워요" : ""}</div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
      {data && open?.kind === "type" && <TypeEditor key={open.id ?? "new"} bot={bot} doc={doc} id={open.id} uses={open.id ? data.usage[open.id] ?? [] : []}
        fieldTypes={fieldTypes} onClose={() => setOpen(null)} save={save} />}
      {data && open?.kind === "role" && <SessionRoleEditor key={open.id ?? "new"} bot={bot} doc={doc} id={open.id} onClose={() => setOpen(null)} save={save} />}
    </main>
  );
}
