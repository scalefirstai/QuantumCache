import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="text-sm text-bny-slate p-6">
      {label}
    </div>
  );
}

export function ErrorBox({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="bg-white border border-bny-mist rounded-lg p-4 max-w-md"
    >
      <p className="font-medium text-sm m-0">{title}</p>
      {detail && <p className="text-xs text-bny-slate mt-1 m-0">{detail}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-xs px-3 py-1.5 rounded-md border border-bny-mist hover:bg-bny-paper"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyBox({ children }: { children: ReactNode }) {
  return (
    <div className="bg-white border border-bny-mist rounded-lg p-6 max-w-md text-sm text-bny-slate">
      {children}
    </div>
  );
}
