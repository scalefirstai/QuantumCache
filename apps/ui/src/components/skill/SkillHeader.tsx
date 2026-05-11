export function SkillHeader({ name, tagline }: { name: string; tagline: string }) {
  return (
    <header className="bg-bny-ink text-white px-5 py-4 rounded-t-lg">
      <div className="flex items-center gap-2.5">
        <span aria-hidden="true" className="text-bny-teal text-xl">
          🔍
        </span>
        <div className="text-base font-medium font-mono">{name}</div>
        <span className="bg-bny-teal text-white text-[10px] px-2 py-0.5 rounded-full font-medium">
          SKILL
        </span>
      </div>
      <div className="text-xs text-bny-sky mt-1.5">{tagline}</div>
    </header>
  );
}
