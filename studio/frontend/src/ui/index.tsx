/* Studio primitives, shadcn/ui style: the source lives here, styled with Tailwind on the tokens of styles.css,
   icons from lucide. Variants, states and keyboard rules are documented in DESIGN-SYSTEM.md. */
import { AlertCircle, CheckCircle2, CircleDashed, Info, Loader2, RotateCw, TriangleAlert, X } from "lucide-react";
import {
  cloneElement, createContext, isValidElement, useCallback, useContext, useEffect, useId, useRef, useState,
  type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactElement, type ReactNode, type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

export const cn = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");

// --- Button ---

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-brand-500 text-on-brand hover:bg-brand-600 shadow-sm",
  secondary: "border border-line bg-surface text-ink hover:bg-sunken",
  ghost: "text-ink-2 hover:bg-sunken hover:text-ink",
  danger: "text-err-fg hover:bg-err-bg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode;
}

export function Button({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button" {...rest} disabled={disabled || loading} aria-busy={loading || undefined}
      className={cn("inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm", VARIANT[variant], className)}
    >
      {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({ label, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" aria-label={label} title={label} {...rest}
      className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted hover:bg-sunken hover:text-ink disabled:opacity-40", className)}>
      {children}
    </button>
  );
}

// --- status ---

export type Tone = "ok" | "warn" | "err" | "idle" | "brand";
const TONE: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok-fg ring-ok-line", warn: "bg-warn-bg text-warn-fg ring-warn-line", err: "bg-err-bg text-err-fg ring-err-line",
  idle: "bg-idle-bg text-idle-fg ring-idle-line", brand: "bg-brand-50 text-brand-700 ring-brand-100",
};
const TONE_ICON: Record<Tone, typeof Info> = { ok: CheckCircle2, warn: TriangleAlert, err: AlertCircle, idle: CircleDashed, brand: Info };

/** A state the user acts on. Never colour alone: an icon goes with it. */
export function StatusChip({ tone, children, icon = true }: { tone: Tone; children: ReactNode; icon?: boolean }) {
  const Icon = TONE_ICON[tone];
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONE[tone])}>
      {icon && <Icon size={12} aria-hidden />}{children}
    </span>
  );
}

/** A word or value inside content (keywords, slot names). Quieter than a status chip. */
export function Tag({ children, tone = "idle" }: { children: ReactNode; tone?: Tone }) {
  return <span className={cn("inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium", TONE[tone].replace(/ring-\S+/, ""))}>{children}</span>;
}

export function Notice({ tone = "brand", title, children, action }: { tone?: Tone; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  const Icon = TONE_ICON[tone];
  return (
    <div role={tone === "err" ? "alert" : undefined} className={cn("flex gap-2.5 rounded-lg px-3.5 py-3 text-[13px] ring-1 ring-inset", TONE[tone])}>
      <Icon size={16} className="mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={cn(!!title && "mt-0.5", "text-ink-2")}>{children}</div>}
      </div>
      {action}
    </div>
  );
}

// --- form fields ---

const control = "w-full rounded-lg border border-line-strong/60 bg-surface px-3 text-sm text-ink placeholder:text-muted outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:bg-sunken disabled:text-muted aria-[invalid=true]:border-err-fg";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cn(control, "h-9", className)} />;
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={cn(control, "py-2 leading-relaxed", className)} />;
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cn(control, "h-9 pr-8", className)} />;

/** Label, hint and error wired to one control by id (aria-describedby, aria-invalid). */
export function Field({ label, hint, error, children, optional, aside }: {
  label: ReactNode; hint?: ReactNode; error?: string | null; children: ReactElement<any>; optional?: boolean; aside?: ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const control = isValidElement<any>(children)
    ? cloneElement<any>(children, { id: children.props.id ?? id, "aria-describedby": [hintId, errId].filter(Boolean).join(" ") || undefined, "aria-invalid": error ? true : undefined })
    : children;
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <label htmlFor={children.props.id ?? id} className="text-sm font-medium text-ink">
          {label}{optional && <span className="ml-1.5 text-xs font-normal text-muted">선택</span>}
        </label>
        {aside}
      </div>
      {control}
      {hint && !error && <p id={hintId} className="mt-1.5 text-xs text-muted">{hint}</p>}
      {error && <p id={errId} className="mt-1.5 flex items-center gap-1 text-xs font-medium text-err-fg"><AlertCircle size={12} aria-hidden />{error}</p>}
    </div>
  );
}

/** Words as removable tags: Enter or comma adds, Backspace on an empty box removes the last one. */
export function WordsInput({ value, onChange, placeholder = "입력 후 Enter", label, tone = "idle", id }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string; label: string; tone?: Tone; id?: string;
}) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const words = raw.split(",").map((w) => w.trim()).filter((w) => w && !value.includes(w));
    if (words.length) onChange([...value, ...words]);
    setText("");
  };
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border border-line-strong/60 bg-surface px-2 py-1.5 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
      {value.map((w) => (
        <span key={w} className={cn("inline-flex items-center gap-0.5 rounded-md py-0.5 pl-2 pr-0.5 text-xs font-medium", TONE[tone].replace(/ring-\S+/, ""))}>
          {w}
          <button type="button" aria-label={`${w} 지우기`} onClick={() => onChange(value.filter((x) => x !== w))}
            className="-my-0.5 grid h-6 w-6 place-items-center rounded opacity-70 hover:bg-black/5 hover:opacity-100"><X size={12} aria-hidden /></button>
        </span>
      ))}
      <input
        id={id} aria-label={label} value={text} placeholder={value.length ? "" : placeholder}
        onChange={(e) => (e.target.value.endsWith(",") ? add(e.target.value) : setText(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); add(text); }
          else if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={() => text.trim() && add(text)}
        className="h-6 min-w-24 flex-1 bg-transparent text-sm text-ink placeholder:text-muted outline-none"
      />
    </div>
  );
}

/** One choice of a few, as a row of toggle buttons (`aria-pressed`; Tab moves between them). */
export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; count?: number }[]; label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg bg-sunken p-0.5">
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}
          className={cn("inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-[13px] font-medium",
            value === o.value ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-ink-2 hover:text-ink")}>
          {o.label}{o.count !== undefined && <span className="num text-xs text-muted">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** A section with a title, a one-line summary while closed, and its body while open. */
export function Disclosure({ title, summary, children, defaultOpen = false, badge }: {
  title: ReactNode; summary?: ReactNode; children: ReactNode; defaultOpen?: boolean; badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <section className="rounded-xl border border-line">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 rounded-xl px-4 py-3 text-left hover:bg-sunken/60">
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-sm font-semibold text-ink">{title}{badge}</span>
          {!open && summary && <span className="mt-0.5 block truncate text-xs text-muted">{summary}</span>}
        </span>
        <span aria-hidden className={cn("mt-0.5 text-muted transition-transform", open && "rotate-180")}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </span>
      </button>
      {open && <div id={id} className="border-t border-line px-4 pb-4 pt-3">{children}</div>}
    </section>
  );
}

// --- overlays ---

function useFocusTrap(active: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!active) return;
    const back = document.activeElement as HTMLElement | null;
    const node = ref.current;
    const items = () => Array.from(node?.querySelectorAll<HTMLElement>('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])') ?? [])
      .filter((el) => !el.hasAttribute("disabled"));
    (node?.querySelector<HTMLElement>("[data-autofocus]") ?? items()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      if (e.key !== "Tab") return;
      const list = items();
      if (!list.length) return;
      const first = list[0], last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    return () => { document.removeEventListener("keydown", onKey, true); back?.focus?.(); };
  }, [active, onClose]);
  return ref;
}

/** Side sheet for one editing task. Esc or the scrim closes it (the owner decides about unsaved changes). */
export function Sheet({ open, onClose, title, subtitle, children, footer, width = 560 }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode; width?: number;
}) {
  const ref = useFocusTrap(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-[var(--scrim)]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} style={{ width }}
        className="relative flex h-full max-w-full flex-col bg-surface shadow-2xl">
        <header className="flex items-start gap-3 border-b border-line px-6 py-4">
          <div className="min-w-0 flex-1">
            {subtitle && <div className="text-xs text-muted">{subtitle}</div>}
            <h2 id={titleId} className="truncate text-lg font-bold text-ink">{title}</h2>
          </div>
          <IconButton label="닫기" onClick={onClose}><X size={18} /></IconButton>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <footer className="flex items-center gap-2 border-t border-line bg-surface px-6 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

export function Dialog({ open, onClose, title, children, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
  const ref = useFocusTrap(open, onClose);
  const titleId = useId();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-[var(--scrim)]" onClick={onClose} aria-hidden />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-surface p-6 shadow-2xl">
        <h2 id={titleId} className="mb-3 text-lg font-bold text-ink">{title}</h2>
        {children}
        {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}

// --- page states: loading, empty, error ---

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton h-4", className)} />;
}

export function LoadingBlock({ rows = 4, label = "불러오는 중" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3 rounded-xl border border-line bg-surface p-5">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className={i % 2 ? "w-2/3" : "w-full"} />)}
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line-strong/50 bg-surface px-6 py-12 text-center">
      {icon && <div className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-brand-50 text-brand-700">{icon}</div>}
      <div className="text-[15px] font-semibold text-ink">{title}</div>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** 을 or 를 after a Korean word, from its last syllable (a final consonant takes 을). */
export function eul(word: string): string {
  const c = word.trim().charCodeAt(word.trim().length - 1);
  if (c < 0xac00 || c > 0xd7a3) return `${word}을(를)`;
  return `${word}${(c - 0xac00) % 28 ? "을" : "를"}`;
}

export function ErrorState({ error, onRetry, what = "내용" }: { error: Error; onRetry?: () => void; what?: string }) {
  return (
    <Notice tone="err" title={`${eul(what)} 불러오지 못했어요`}
      action={onRetry && <Button size="sm" variant="secondary" icon={<RotateCw size={14} />} onClick={onRetry}>다시 시도</Button>}>
      서버가 켜져 있는지 확인해 보세요. 받은 응답: {error.message}
    </Notice>
  );
}

// --- toast: one polite live region for "saved" and similar ---

interface ToastItem { id: number; tone: Tone; text: string }
const ToastCtx = createContext<(text: string, tone?: Tone) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((text: string, tone: Tone = "ok") => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, tone, text }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-5 left-1/2 z-[60] flex -translate-x-1/2 flex-col items-center gap-2">
        {items.map((t) => {
          const Icon = TONE_ICON[t.tone];
          return (
            <div key={t.id} className="pointer-events-auto flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-medium text-surface shadow-lg">
              <Icon size={15} aria-hidden />{t.text}
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

export function PageHeader({ title, description, actions, count }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; count?: number }) {
  return (
    <div className="mb-6 flex flex-wrap items-end gap-x-4 gap-y-3">
      <div className="min-w-0 flex-1">
        <h1 className="text-xl font-bold tracking-tight text-ink">
          {title}{count !== undefined && <span className="num ml-2 text-sm font-medium text-muted">{count}개</span>}
        </h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
