export function fmtUsd(n: number, compact = false): string {
  if (!Number.isFinite(n)) return "—";
  if (compact && Math.abs(n) >= 1_000_000_000) {
    return `$${(n / 1_000_000_000).toFixed(1)}B`;
  }
  if (compact && Math.abs(n) >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(1)}M`;
  }
  if (compact && Math.abs(n) >= 1_000) {
    return `$${(n / 1_000).toFixed(0)}K`;
  }
  return "$" + Math.round(n).toLocaleString();
}

export function fmtPct(n: number, digits = 1): string {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

export function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  return d.replace("T", " ").replace(/\+00:00$/, " UTC");
}
