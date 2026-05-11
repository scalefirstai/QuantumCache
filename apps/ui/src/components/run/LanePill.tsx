import type { Lane } from "@/types/run";

const styles: Record<Lane, string> = {
  knowledge: "bg-lane-knowledgeBg text-lane-knowledgeFg",
  canonical: "bg-lane-canonicalBg text-lane-canonicalFg",
  audit: "bg-lane-auditBg text-lane-auditFg",
};

const darkStyles: Record<Lane, string> = {
  knowledge: "dark:bg-[#085041] dark:text-[#9FE1CB]",
  canonical: "dark:bg-[#3C3489] dark:text-[#CECBF6]",
  audit: "dark:bg-[#444441] dark:text-[#D3D1C7]",
};

export function LanePill({ lane }: { lane: Lane }) {
  return (
    <span
      data-lane={lane}
      className={[
        "inline-block text-[11px] px-2 py-px rounded-full font-medium",
        styles[lane],
        darkStyles[lane],
      ].join(" ")}
    >
      {lane}
    </span>
  );
}
