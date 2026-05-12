import { useEffect, useMemo, useState } from "react";
import { listSkills } from "@/api/agents";
import type { SkillSummary } from "@/types/agent";

export function SkillsRoute() {
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    listSkills().then(setSkills).catch((e) => setErr(String(e)));
  }, []);

  const categories = useMemo(
    () => ["all", ...Array.from(new Set(skills?.map((s) => s.category) ?? []))],
    [skills],
  );
  const filtered = useMemo(
    () => (skills ?? []).filter((s) => filter === "all" || s.category === filter),
    [skills, filter],
  );

  if (err) return <pre className="px-6 py-5 text-xs">{err}</pre>;
  if (!skills) return <div className="px-6 py-5 text-sm text-bny-fog">Loading…</div>;

  return (
    <div className="px-6 py-5" data-testid="skills-root">
      <header className="mb-4">
        <h1 className="text-xl font-semibold leading-tight">Skills</h1>
        <p className="text-sm text-bny-fog mt-1">
          Tools the agents call. Code-defined today; this catalog is read-only.
        </p>
      </header>
      <div className="mb-3 flex gap-2 text-xs flex-wrap" data-testid="category-filter">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setFilter(c)}
            className={
              "px-2 py-1 rounded border " +
              (filter === c
                ? "bg-bny-teal text-white border-bny-teal"
                : "border-bny-mist text-bny-slate hover:bg-bny-paper")
            }
          >
            {c}
          </button>
        ))}
      </div>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="skills-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Name</Th>
              <Th>Category</Th>
              <Th>Owner</Th>
              <Th>Signature</Th>
              <Th>Used by</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => (
              <tr
                key={s.id}
                className="border-t border-bny-mist hover:bg-bny-paper/60"
                data-testid={`skill-row-${s.id}`}
              >
                <Td>
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs text-bny-fog">{s.description}</div>
                </Td>
                <Td className="text-xs">{s.category}</Td>
                <Td className="text-xs font-mono">{s.ownedBy}</Td>
                <Td className="text-xs font-mono">{s.signature}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {s.usedBy.length === 0 ? (
                      <span className="text-xs text-bny-fog">—</span>
                    ) : (
                      s.usedBy.map((u) => (
                        <span
                          key={u}
                          className="text-[10px] px-1.5 py-0.5 rounded bg-bny-paper border border-bny-mist text-bny-slate"
                        >
                          {u}
                        </span>
                      ))
                    )}
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const Th = ({ children }: { children: React.ReactNode }) => (
  <th className="text-left font-medium px-3 py-2">{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-top ${className}`}>{children}</td>
);
