import { Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type Bot } from "../api";
import { useFetch, useShell, useUnsavedWarning } from "../hooks";
import type { SlotListsResponse } from "../lib/wording";
import { ErrorState, Field, IconButton, LoadingBlock, Select, useToast } from "../ui";
import { SaveBar } from "./SaveBar";

type Draft = { sensitive: string[]; readback: { slot: string; format: string }[] };

/** 민감 속성 (keypad only) and 다시 읽어 줄 속성 (read back after filling): shared by every language of the domain. */
export default function SlotLists({ bot }: { bot: Bot }) {
  const { refresh } = useShell();
  const toast = useToast();
  const { data, error, loading, reload, setData } = useFetch<SlotListsResponse>(`/domains/${bot.domain}/slot-lists`, [bot.shared_revision]);
  const initial = useMemo<Draft | null>(() => data && { sensitive: data.sensitive.slots, readback: data.readback.slots }, [data]);
  const [d, setD] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [fieldErr, setFieldErr] = useState<Record<string, string>>({});
  useEffect(() => { setD(initial); setFieldErr({}); }, [initial]);
  const dirty = !!d && !!initial && JSON.stringify(d) !== JSON.stringify(initial);
  useUnsavedWarning(dirty);

  if (error) return <ErrorState error={error} onRetry={reload} what="속성 목록" />;
  if (loading || !data || !d || !initial) return <LoadingBlock rows={3} />;

  const freeSensitive = data.candidates.sensitive.filter((a) => !d.sensitive.includes(a));
  const freeReadback = data.candidates.readback.filter((a) => !d.readback.some((r) => r.slot === a));
  const fmt = (call: string) => data.formats.find((f) => f.call === call)?.label ?? call;
  const askedIn = (a: string) => (data.asked_in[a] ?? []).join(", ");
  const unused = (a: string) => !(a in data.asked_in);

  const save = async () => {
    setBusy(true); setSaveError(""); setFieldErr({});
    try {
      const out = await api.put<SlotListsResponse>(`/domains/${bot.domain}/slot-lists`, {
        ...d, sensitive_revision: data.sensitive.revision, readback_revision: data.readback.revision,
      });
      setData(out); refresh();
      toast(`저장했어요. 상담봇 ${out.affects_bots.length}개를 다시 검증해야 해요`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422 && e.body?.detail?.problems) {
        setFieldErr(Object.fromEntries(e.body.detail.problems.map((p: any) => [p.field, p.message])));
        setSaveError("엔진이 받아들이지 않는 곳이 있어요. 표시된 곳을 고쳐 주세요.");
      } else setSaveError(e instanceof ApiError && e.status === 409 ? "다른 곳에서 먼저 바뀌었어요. 새로 불러온 뒤 다시 고쳐 주세요." : (e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={(ev) => { ev.preventDefault(); if (dirty) void save(); }} className="rounded-2xl border border-line bg-surface">
      <div className="grid gap-8 px-6 py-6 md:grid-cols-2">
        <section aria-labelledby="sens-h">
          <h3 id="sens-h" className="text-sm font-semibold text-ink">키패드로만 받는 속성</h3>
          <p className="mb-3 mt-1 text-xs text-muted">비밀번호처럼 말로 들으면 안 되는 속성이에요. 고객이 말로 답하면 키패드로 누르라고 안내해요. 숫자 형식으로 받는 속성만 고를 수 있어요.</p>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {d.sensitive.length === 0 && <li className="px-4 py-3 text-[13px] text-muted">정한 속성이 없어요.</li>}
            {d.sensitive.map((a) => (
              <li key={a} className="flex items-center gap-2 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <code className="text-[13px] text-ink">{a}</code>
                  <div className="truncate text-xs text-muted">{unused(a) ? "받는 시나리오가 없어요" : `받는 곳: ${askedIn(a)}`}</div>
                  {fieldErr[`sensitive.${a}`] && <p className="mt-1 text-xs font-medium text-err-fg">{fieldErr[`sensitive.${a}`]}</p>}
                </div>
                <IconButton label={`${a} 빼기`} onClick={() => setD({ ...d, sensitive: d.sensitive.filter((x) => x !== a) })}><Trash2 size={15} /></IconButton>
              </li>
            ))}
          </ul>
          <div className="mt-3 max-w-xs">
            <Field label="속성 추가" hint={freeSensitive.length ? undefined : "추가할 수 있는 숫자 속성이 없어요."}>
              <Select value="" disabled={!freeSensitive.length} onChange={(e) => e.target.value && setD({ ...d, sensitive: [...d.sensitive, e.target.value] })}>
                <option value="">고르세요</option>
                {freeSensitive.map((a) => <option key={a} value={a}>{a}</option>)}
              </Select>
            </Field>
          </div>
        </section>

        <section aria-labelledby="rb-h">
          <h3 id="rb-h" className="text-sm font-semibold text-ink">값을 받으면 다시 읽어 줄 속성</h3>
          <p className="mb-3 mt-1 text-xs text-muted">잘못 알아들은 값을 고객이 바로잡을 수 있게, 값을 받는 즉시 한 번 읽어 줘요. 읽는 방식을 같이 정해요.</p>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {d.readback.length === 0 && <li className="px-4 py-3 text-[13px] text-muted">정한 속성이 없어요.</li>}
            {d.readback.map((r, i) => (
              <li key={r.slot} className="flex items-center gap-2 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <code className="text-[13px] text-ink">{r.slot}</code>
                  <div className="truncate text-xs text-muted">{unused(r.slot) ? "받는 시나리오가 없어요" : `받는 곳: ${askedIn(r.slot)}`}</div>
                  {fieldErr[`readback.${r.slot}`] && <p className="mt-1 text-xs font-medium text-err-fg">{fieldErr[`readback.${r.slot}`]}</p>}
                </div>
                <Select aria-label={`${r.slot} 읽는 방식`} className="w-44" value={r.format}
                  onChange={(e) => setD({ ...d, readback: d.readback.map((x, j) => (j === i ? { ...x, format: e.target.value } : x)) })}>
                  {!data.formats.some((f) => f.call === r.format) && <option value={r.format}>{fmt(r.format)}</option>}
                  {data.formats.map((f) => <option key={f.call} value={f.call}>{f.label}</option>)}
                </Select>
                <IconButton label={`${r.slot} 빼기`} onClick={() => setD({ ...d, readback: d.readback.filter((_, j) => j !== i) })}><Trash2 size={15} /></IconButton>
              </li>
            ))}
          </ul>
          <div className="mt-3 max-w-xs">
            <Field label="속성 추가" hint={freeReadback.length ? undefined : "추가할 속성이 없어요."}>
              <Select value="" disabled={!freeReadback.length}
                onChange={(e) => e.target.value && setD({ ...d, readback: [...d.readback, { slot: e.target.value, format: data.formats[0]?.call ?? "count" }] })}>
                <option value="">고르세요</option>
                {freeReadback.map((a) => <option key={a} value={a}>{a}</option>)}
              </Select>
            </Field>
          </div>
        </section>
      </div>
      <SaveBar dirty={dirty} busy={busy} invalid={false} error={saveError}
        note={`${data.affects_bots.length}개 상담봇에 모두 적용돼요. 저장 후 검증과 게시가 필요해요`} onReset={() => { setD(initial); setFieldErr({}); setSaveError(""); }} />
    </form>
  );
}
