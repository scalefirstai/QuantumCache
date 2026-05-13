import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5 flex items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <div className="text-[10px] uppercase tracking-[0.18em] text-bny-slate mb-1">
            {eyebrow}
          </div>
        )}
        <h1 className="text-xl font-semibold leading-tight">{title}</h1>
        {subtitle && (
          <p className="text-sm text-bny-slate mt-1 max-w-2xl">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function PrimaryButton({
  onClick,
  children,
  testId,
  type = "button",
  disabled,
}: {
  onClick?: () => void;
  children: ReactNode;
  testId?: string;
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  return (
    <button
      type={type}
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className="text-sm font-medium px-3 py-1.5 rounded-md bg-bny-teal text-white hover:bg-bny-ink focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-bny-teal disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  onClick,
  children,
  testId,
  type = "button",
  tone = "neutral",
}: {
  onClick?: () => void;
  children: ReactNode;
  testId?: string;
  type?: "button" | "submit";
  tone?: "neutral" | "danger";
}) {
  const palette =
    tone === "danger"
      ? "text-bny-danger border-bny-danger/40 hover:bg-bny-danger/10"
      : "text-bny-ink border-bny-mist hover:bg-bny-paper";
  return (
    <button
      type={type}
      data-testid={testId}
      onClick={onClick}
      className={`text-sm px-3 py-1.5 rounded-md border bg-white ${palette} focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-bny-teal`}
    >
      {children}
    </button>
  );
}

export function FilterRow({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3 text-sm">{children}</div>
  );
}

export function TagPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "knowledge" | "canonical" | "audit" | "danger" | "ok";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-bny-paper text-bny-slate border-bny-mist",
    knowledge: "bg-lane-knowledgeBg text-lane-knowledgeFg border-transparent",
    canonical: "bg-lane-canonicalBg text-lane-canonicalFg border-transparent",
    audit: "bg-lane-auditBg text-lane-auditFg border-transparent",
    danger: "bg-bny-danger/10 text-bny-danger border-bny-danger/30",
    ok: "bg-bny-ok/10 text-bny-ok border-bny-ok/30",
  };
  return (
    <span
      className={`inline-flex items-center text-[10px] px-1.5 py-0.5 rounded font-medium border ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  testId,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 bg-bny-ink/40 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      data-testid={testId}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg border border-bny-mist max-w-xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-5 py-3 border-b border-bny-mist flex items-center justify-between">
          <h2 className="text-base font-medium">{title}</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="text-bny-fog hover:text-bny-ink rounded-md w-7 h-7 inline-flex items-center justify-center hover:bg-bny-paper"
            data-testid="modal-close"
          >
            ×
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function FormField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block mb-3 text-sm">
      <span className="block font-medium text-bny-ink mb-1">{label}</span>
      {children}
      {hint && <span className="block text-xs text-bny-fog mt-1">{hint}</span>}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={
        "w-full px-2.5 py-1.5 rounded-md border border-bny-mist bg-white text-sm focus:outline-none focus:ring-2 focus:ring-bny-teal focus:border-transparent " +
        (props.className ?? "")
      }
    />
  );
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={
        "w-full px-2.5 py-1.5 rounded-md border border-bny-mist bg-white text-sm focus:outline-none focus:ring-2 focus:ring-bny-teal focus:border-transparent " +
        (props.className ?? "")
      }
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={
        "w-full px-2.5 py-1.5 rounded-md border border-bny-mist bg-white text-sm focus:outline-none focus:ring-2 focus:ring-bny-teal focus:border-transparent " +
        (props.className ?? "")
      }
    />
  );
}

export function Field({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-bny-fog">
        {label}
      </div>
      <div className="text-sm mt-0.5 break-words">{value}</div>
    </div>
  );
}

export function VerdictPill({ verdict }: { verdict: string }) {
  const map: Record<string, string> = {
    pass: "ok",
    halt: "danger",
    sme: "audit",
    review: "neutral",
  };
  const tone = (map[verdict?.toLowerCase?.() ?? ""] ?? "neutral") as
    | "ok"
    | "danger"
    | "audit"
    | "neutral";
  return <TagPill tone={tone}>{verdict || "—"}</TagPill>;
}

