import { Copy, FilePlus2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type BotDetail, type BotSettings, type Domain } from "../api";
import { domainName, langName } from "../copy";
import { useFetch, useShell } from "../hooks";
import { paths } from "../paths";
import { Button, cn, eul, Field, Input, Select, Sheet, useToast } from "../ui";

const NEW = "__new__";
export const DOMAIN_ID = /^[a-z][a-z0-9-]{1,39}$/;

/** An id from an ASCII name ("Dental Care" -> "dental-care"); nothing when the name is not ASCII. */
export function suggestId(name: string): string {
  if (!/^[\x20-\x7e]*$/.test(name)) return "";
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^[^a-z]+|-+$/g, "").slice(0, 40);
}

/** What is wrong with a new business id, or null. */
export function domainIdProblem(id: string, existing: string[], inRepo: string[]): string | null {
  if (!id) return "영문 ID를 넣어 주세요";
  if (!DOMAIN_ID.test(id)) return "영어 소문자로 시작하고, 소문자, 숫자, - 만 써서 2~40자로 넣어 주세요";
  if (existing.includes(id)) return "이미 있는 업종이에요. 위 목록에서 고르세요";
  if (inRepo.includes(id)) return "저장소의 domains 폴더에 같은 업종이 있어요. 홈에서 가져오기로 불러오세요";
  return null;
}

function Choice({ name, checked, disabled, onChange, icon, title, children }: {
  name: string; checked: boolean; disabled?: boolean; onChange: () => void; icon?: ReactNode; title: ReactNode; children?: ReactNode;
}) {
  return (
    <label className={cn("flex gap-3 rounded-xl border p-3.5 text-left",
      disabled ? "cursor-not-allowed border-line bg-sunken/50 opacity-70" : "cursor-pointer hover:border-brand-500",
      checked && !disabled ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-line bg-surface")}>
      <input type="radio" name={name} className="mt-1 accent-brand-600" checked={checked}
        disabled={disabled} onChange={onChange} />
      {icon && <span className="mt-0.5 text-muted" aria-hidden>{icon}</span>}
      <span className="min-w-0">
        <span className="block text-sm font-semibold text-ink">{title}</span>
        {children && <span className="mt-0.5 block text-[13px] leading-relaxed text-muted">{children}</span>}
      </span>
    </label>
  );
}

function Part({ step, title, children }: { step: number; title: string; children: ReactNode }) {
  return (
    <fieldset className="border-t border-line py-5 first:border-t-0 first:pt-0">
      <legend className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
        <span className="num grid h-5 w-5 place-items-center rounded-full bg-sunken text-xs text-ink-2" aria-hidden>{step}</span>{title}
      </legend>
      <div className="grid gap-3">{children}</div>
    </fieldset>
  );
}

export default function NewBot({ domains, inRepo, onClose }: { domains: Domain[]; inRepo: string[]; onClose: () => void }) {
  const { refresh } = useShell();
  const toast = useToast();
  const navigate = useNavigate();
  const { data: langs } = useFetch<string[]>("/languages");
  const [domain, setDomain] = useState(domains[0]?.slug ?? NEW);
  const [domainTitle, setDomainTitle] = useState("");
  const [domainId, setDomainId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [lang, setLang] = useState("");
  const [start, setStart] = useState<"empty" | "copy">("empty");
  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [reprompts, setReprompts] = useState(2);
  const [handoff, setHandoff] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const isNew = domain === NEW;
  const dom = domains.find((d) => d.slug === domain);
  const taken = new Set(dom?.bots.map((b) => b.lang) ?? []);
  const free = (langs ?? []).filter((l) => !taken.has(l));
  const sibling = dom?.bots.find((b) => b.lang !== lang) ?? null;
  const name = isNew ? domainTitle.trim() : domainName(domain, dom?.title);

  // a language the business already has cannot be picked; move to the first free one
  useEffect(() => { if (langs && (!lang || taken.has(lang))) setLang(free[0] ?? ""); }, [langs, domain]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!sibling) setStart("empty"); }, [sibling]);
  useEffect(() => { if (!idTouched) setDomainId(suggestId(domainTitle)); }, [domainTitle, idTouched]);
  useEffect(() => { if (!titleTouched) setTitle(name ? `${name} 상담봇` : ""); }, [name, titleTouched]);

  // a copy starts from the sibling's defaults
  const { data: srcSettings } = useFetch<BotSettings>(start === "copy" && sibling ? `/bots/${sibling.slug}/settings` : null);
  useEffect(() => {
    if (start === "copy" && srcSettings) {
      setReprompts(srcSettings.engine.ask.max_reprompts);
      setHandoff(srcSettings.studio_only.handoff_number ?? "");
    }
  }, [start, srcSettings]);

  const idProblem = isNew ? domainIdProblem(domainId, domains.map((d) => d.slug), inRepo) : null;
  const problems = useMemo(() => ({
    domainTitle: isNew && !domainTitle.trim() ? "업종 이름을 넣어 주세요" : null,
    lang: langs && !free.length ? "이 업종은 모든 언어의 상담봇이 이미 있어요" : null,
    title: !title.trim() ? "이름을 넣어 주세요" : null,
    reprompts: !Number.isInteger(reprompts) || reprompts < 0 ? "0 이상의 정수를 넣어 주세요" : null,
    handoff: /^[0-9+\-() ]*$/.test(handoff) ? null : "숫자, 공백, + - ( ) 만 쓸 수 있어요",
  }), [isNew, domainTitle, langs, free.length, title, reprompts, handoff]);
  const blocked = !!idProblem || Object.values(problems).some(Boolean) || !lang;

  const create = async () => {
    setBusy(true); setError("");
    try {
      const b = await api.post<BotDetail>("/bots", {
        domain: isNew ? domainId : domain, domain_title: isNew ? domainTitle.trim() : undefined, lang, title: title.trim(),
        start, copy_from: start === "copy" ? sibling?.slug : undefined,
        settings: { engine: { ask: { max_reprompts: reprompts } }, studio_only: { handoff_number: handoff.trim() || null } },
      });
      toast(start === "copy" ? `${eul(b.title)} 만들었어요. 번역할 곳을 표시해 뒀어요` : `${eul(b.title)} 만들었어요`);
      refresh();
      onClose();
      navigate(paths.bot(b.slug));
    } catch (e) {
      const reason = e instanceof ApiError ? e.body?.detail?.reason : null;
      setError(reason === "exists" ? "이 업종에는 그 언어의 상담봇이 이미 있어요."
        : reason === "in_repo" ? "저장소의 domains 폴더에 같은 업종이 있어요. 홈에서 가져오기로 불러오세요."
        : (e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <Sheet open onClose={onClose} title="새 상담봇" subtitle="업종 하나와 언어 하나가 상담봇 하나예요"
      footer={<>
        <span className="flex-1 text-[13px] font-medium text-err-fg" role="status">{error}</span>
        <Button onClick={onClose}>취소</Button>
        <Button variant="primary" loading={busy} disabled={blocked} onClick={create}>만들기</Button>
      </>}>
      <form onSubmit={(e) => { e.preventDefault(); if (!blocked) void create(); }}>
        <Part step={1} title="업종">
          <Field label="업종" hint={dom ? `같은 업종의 상담봇은 API 연결과 속성 종류를 함께 써요.` : undefined}>
            <Select data-autofocus value={domain} onChange={(e) => setDomain(e.target.value)}>
              {domains.map((d) => (
                <option key={d.slug} value={d.slug}>{domainName(d.slug, d.title)} ({d.bots.map((b) => langName(b.lang)).join(", ") || "상담봇 없음"})</option>
              ))}
              <option value={NEW}>새 업종 만들기</option>
            </Select>
          </Field>
          {isNew && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="업종 이름" error={domainTitle && problems.domainTitle}>
                <Input value={domainTitle} placeholder="예: 병원 예약" onChange={(e) => setDomainTitle(e.target.value)} />
              </Field>
              <Field label="영문 ID" hint="게시 파일의 폴더 이름이 돼요. 나중에 바꿀 수 없어요." error={(idTouched || domainTitle) ? idProblem : null}>
                <Input className="font-mono" value={domainId} placeholder="예: clinic"
                  onChange={(e) => { setIdTouched(true); setDomainId(e.target.value.trim().toLowerCase()); }} />
              </Field>
            </div>
          )}
        </Part>

        <Part step={2} title="언어">
          <div role="radiogroup" aria-label="언어" className="grid gap-2 sm:grid-cols-2">
            {(langs ?? []).map((l) => (
              <Choice key={l} name="lang" checked={lang === l} disabled={taken.has(l)} onChange={() => setLang(l)} title={langName(l)}>
                {taken.has(l) ? "이 업종에 이미 있어요" : undefined}
              </Choice>
            ))}
          </div>
          {problems.lang && <p className="text-xs font-medium text-err-fg">{problems.lang}</p>}
          <p className="text-xs text-muted">엔진이 읽을 수 있는 언어만 보여요.</p>
        </Part>

        <Part step={3} title="시작 방식">
          <div role="radiogroup" aria-label="시작 방식" className="grid gap-2">
            <Choice name="start" checked={start === "empty"} onChange={() => setStart("empty")} icon={<FilePlus2 size={18} />} title="빈 상담봇">
              질문과 시나리오 없이 시작해요. 못 알아들었을 때 하는 말 같은 기본 문구는 고른 언어로 넣어 드려요.
            </Choice>
            <Choice name="start" checked={start === "copy"} disabled={!sibling} onChange={() => setStart("copy")} icon={<Copy size={18} />}
              title={sibling ? `${langName(sibling.lang)} 상담봇 복사` : "다른 언어 상담봇 복사"}>
              {sibling
                ? "질문, 시나리오, 기본 설정을 그대로 가져와요. 문구는 원래 언어로 남아 있으니 번역할 곳으로 표시해 둘게요."
                : "같은 업종에 다른 언어 상담봇이 있을 때 쓸 수 있어요."}
            </Choice>
          </div>
        </Part>

        <Part step={4} title="기본 설정">
          <Field label="이름" hint="스튜디오에서만 보여요." error={problems.title}>
            <Input value={title} onChange={(e) => { setTitleTouched(true); setTitle(e.target.value); }} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="기본 재질문 횟수" hint="0이면 다시 묻지 않아요." error={problems.reprompts}>
              <div className="relative">
                <Input type="number" inputMode="numeric" min={0} className="num pr-10" value={Number.isNaN(reprompts) ? "" : reprompts}
                  onChange={(e) => setReprompts(e.target.value === "" ? NaN : Number(e.target.value))} />
                <span className="pointer-events-none absolute right-3 top-2 text-sm text-muted" aria-hidden>번</span>
              </div>
            </Field>
            <Field label="상담사 연결 번호" optional error={problems.handoff}>
              <Input inputMode="tel" value={handoff} placeholder="예: 1588-0000" onChange={(e) => setHandoff(e.target.value)} />
            </Field>
          </div>
          <p className="text-xs text-muted">나머지 설정은 만든 뒤 개요에서 바꿀 수 있어요.</p>
        </Part>
      </form>
    </Sheet>
  );
}
