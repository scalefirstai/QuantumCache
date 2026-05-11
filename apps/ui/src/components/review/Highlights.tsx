export function Highlights({
  whatWentWell,
  goals,
}: {
  whatWentWell: string[];
  goals: string[];
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
      <Card title="What went well" accent="border-l-bny-teal" items={whatWentWell} testid="went-well" />
      <Card title="Goals · next 90 days" accent="border-l-bny-ochre" items={goals} testid="goals" />
    </div>
  );
}

function Card({
  title,
  accent,
  items,
  testid,
}: {
  title: string;
  accent: string;
  items: string[];
  testid: string;
}) {
  return (
    <section
      data-testid={testid}
      className={`bg-white border border-bny-mist border-l-[3px] ${accent} px-4 py-3.5`}
    >
      <h2 className="text-xs font-medium text-bny-ink m-0 mb-2">{title}</h2>
      <ul className="text-xs text-bny-slate leading-[1.7] list-disc pl-4 m-0">
        {items.map((it) => (
          <li key={it}>{it}</li>
        ))}
      </ul>
    </section>
  );
}
