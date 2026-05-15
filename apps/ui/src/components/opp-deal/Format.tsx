import type { ReactNode } from "react";

const STATUS_TONE: Record<string, string> = {
  intake: "bg-bny-paper text-bny-slate border-bny-mist",
  resolving: "bg-bny-paper text-bny-slate border-bny-mist",
  scoping: "bg-lane-canonicalBg text-lane-canonicalFg border-transparent",
  ddq: "bg-lane-canonicalBg text-lane-canonicalFg border-transparent",
  complexity: "bg-bny-teal/10 text-bny-teal border-bny-teal/30",
  cost_capacity: "bg-bny-teal/10 text-bny-teal border-bny-teal/30",
  pricing: "bg-bny-teal/10 text-bny-teal border-bny-teal/30",
  operating_model: "bg-bny-teal/10 text-bny-teal border-bny-teal/30",
  approval: "bg-bny-ochre/10 text-bny-ochre border-bny-ochre/30",
  won: "bg-bny-ok/10 text-bny-ok border-bny-ok/30",
  lost: "bg-bny-danger/10 text-bny-danger border-bny-danger/30",
  withdrawn: "bg-bny-paper text-bny-fog border-bny-mist",
};

export function StatusPill({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? STATUS_TONE.intake;
  return (
    <span
      className={`inline-flex items-center text-[10px] px-1.5 py-0.5 rounded font-medium border ${tone}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function Card({
  title,
  children,
  actions,
  testId,
}: {
  title: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  testId?: string;
}) {
  return (
    <section
      data-testid={testId}
      className="bg-white border border-bny-mist rounded-lg p-4 mb-4"
    >
      <header className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </header>
      {children}
    </section>
  );
}

export function KeyValueGrid({
  items,
}: {
  items: Array<{ label: string; value: ReactNode; testId?: string }>;
}) {
  return (
    <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-3">
      {items.map((it) => (
        <div key={it.label}>
          <dt className="text-[10px] uppercase tracking-wider text-bny-fog">
            {it.label}
          </dt>
          <dd className="text-sm mt-0.5 break-words" data-testid={it.testId}>
            {it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="text-sm text-bny-slate bg-bny-paper border border-dashed border-bny-mist rounded-md p-4 text-center">
      {children}
    </div>
  );
}
