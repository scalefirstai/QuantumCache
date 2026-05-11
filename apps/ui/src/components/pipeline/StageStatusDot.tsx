import type { StageStatus } from "@/types/pipeline";

const COLORS: Record<StageStatus, { bg: string; fg: string; ring: string }> = {
  pass: { bg: "bg-[#E1F5EE]", fg: "text-bny-ok",     ring: "ring-bny-ok/40" },
  warn: { bg: "bg-[#FAEEDA]", fg: "text-bny-ochre",  ring: "ring-bny-ochre/40" },
  halt: { bg: "bg-[#FCEBEB]", fg: "text-bny-danger", ring: "ring-bny-danger/40" },
  skip: { bg: "bg-bny-haze",  fg: "text-bny-fog",    ring: "ring-bny-fog/30" },
};

const SYMBOLS: Record<StageStatus, string> = {
  pass: "✓",
  warn: "!",
  halt: "✗",
  skip: "–",
};

export function StageStatusDot({
  status,
  size = "md",
}: {
  status: StageStatus;
  size?: "sm" | "md";
}) {
  const c = COLORS[status];
  const dim = size === "sm" ? "w-4 h-4 text-[10px]" : "w-5 h-5 text-[11px]";
  return (
    <span
      aria-label={status}
      data-status={status}
      className={[
        "inline-flex items-center justify-center rounded-full font-medium leading-none ring-1",
        dim,
        c.bg,
        c.fg,
        c.ring,
      ].join(" ")}
    >
      {SYMBOLS[status]}
    </span>
  );
}
