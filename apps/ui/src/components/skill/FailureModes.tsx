export function FailureModes({ items }: { items: string[] }) {
  return (
    <section
      data-testid="failure-modes"
      className="bg-white border border-bny-mist border-l-4 border-l-bny-ochre rounded-lg px-4 py-3.5"
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span aria-hidden="true" className="text-bny-ochre">
          ⓘ
        </span>
        <h2 className="text-xs font-medium text-bny-ink m-0">
          Failure modes worth knowing
        </h2>
      </div>
      <ul className="text-xs text-bny-slate leading-[1.7] pl-4 list-disc m-0">
        {items.map((it) => (
          <li key={it}>{it}</li>
        ))}
      </ul>
    </section>
  );
}
