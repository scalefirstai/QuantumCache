import type { SkillIO as SkillIOItem } from "@/types/skill";

export function SkillIOTable({
  title,
  items,
}: {
  title: string;
  items: SkillIOItem[];
}) {
  return (
    <section className="bg-white border border-bny-mist rounded-lg px-4 py-3.5">
      <h2 className="text-[13px] font-medium text-bny-ink mb-3 m-0">{title}</h2>
      <dl className="flex flex-col gap-2 text-xs">
        {items.map((io) => (
          <div
            key={io.name}
            className="grid gap-2.5"
            style={{ gridTemplateColumns: "100px 1fr" }}
          >
            <dt className="text-bny-teal font-mono">{io.name}</dt>
            <dd className="text-bny-slate m-0">{io.description}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
