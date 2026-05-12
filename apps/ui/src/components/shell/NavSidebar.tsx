import { Link, type LinkProps } from "@tanstack/react-router";

type NavLink = { label: string } & Pick<LinkProps, "to" | "params">;

const links: NavLink[] = [
  { to: "/", label: "Home" },
  {
    to: "/runs/$runId",
    params: { runId: "run_20260510T125906_2b46b0fd" },
    label: "Run · AFME 1.5.2",
  },
  {
    to: "/employees/$de",
    params: { de: "aria" },
    label: "Aria · console",
  },
  {
    to: "/employees/$de/review/$period",
    params: { de: "aria", period: "q1-2026" },
    label: "Aria · Q1 review",
  },
  {
    to: "/skills/$skillId",
    params: { skillId: "retrieval-hybrid" },
    label: "Skill · Retrieval.hybrid",
  },
];

const autogenLinks: NavLink[] = [
  { to: "/agents", label: "Agents" },
  { to: "/models", label: "Models" },
  { to: "/skills", label: "Skills" },
  { to: "/playground", label: "Playground" },
];

export function NavSidebar() {
  return (
    <aside
      className="border-r border-bny-mist bg-white sticky top-0 h-screen px-4 py-5"
      aria-label="primary"
    >
      <div className="flex items-center gap-2 px-2 py-1 mb-4">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-bny-teal text-white text-xs font-medium">
          DE
        </span>
        <div>
          <div className="text-xs text-bny-fog leading-none">BNY DDQ</div>
          <div className="text-sm font-medium leading-tight">Aria</div>
        </div>
      </div>
      <nav className="flex flex-col gap-1">
        {links.map((l) => (
          <Link
            key={l.label}
            to={l.to}
            params={l.params}
            className="text-[13px] px-2 py-1.5 rounded-md text-bny-slate hover:bg-bny-paper [&.active]:bg-bny-tealLight [&.active]:text-bny-ink [&.active]:font-medium"
            activeProps={{ className: "active" }}
          >
            {l.label}
          </Link>
        ))}
        <div className="text-[10px] uppercase tracking-wider text-bny-fog mt-4 px-2">
          AutoGen Lite
        </div>
        {autogenLinks.map((l) => (
          <Link
            key={l.label}
            to={l.to}
            params={l.params}
            className="text-[13px] px-2 py-1.5 rounded-md text-bny-slate hover:bg-bny-paper [&.active]:bg-bny-tealLight [&.active]:text-bny-ink [&.active]:font-medium"
            activeProps={{ className: "active" }}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
