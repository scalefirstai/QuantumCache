import { Link, type LinkProps } from "@tanstack/react-router";

type NavLink = {
  label: string;
  hint?: string;
} & Pick<LinkProps, "to" | "params">;

type NavSection = {
  title: string;
  caption?: string;
  links: NavLink[];
};

// Navigation is grouped around the deal lifecycle, not around the apps that
// implement each stage. "Deal pipeline" is the home. The DDQ pipeline, Aria
// console, agents and skills are surfaces owned by partner teams that show
// up as workflow inputs to a deal.
const SECTIONS: NavSection[] = [
  {
    title: "Deal pipeline",
    caption: "Opportunities owned by the deal team",
    links: [
      { to: "/", label: "Home" },
      { to: "/opportunities", label: "Opportunities" },
      { to: "/sources", label: "eCRM inbox", hint: "Inbound RFPs awaiting promote" },
    ],
  },
  {
    title: "Workflow teams",
    caption: "Stage owners — DDQ, controls, performance",
    links: [
      {
        to: "/pipeline/$ddqId",
        params: { ddqId: "ddq_8db64d9cb6c5" },
        label: "DDQ pipeline",
        hint: "Owned by DDQ team",
      },
      {
        to: "/employees/$de",
        params: { de: "aria" },
        label: "Aria · DDQ console",
      },
      {
        to: "/employees/$de/review/$period",
        params: { de: "aria", period: "q1-2026" },
        label: "Aria · Q1 review",
      },
      {
        to: "/runs/$runId",
        params: { runId: "run_20260510T125906_2b46b0fd" },
        label: "Sealed run walkthrough",
      },
    ],
  },
  {
    title: "Reference",
    caption: "Knowledge, rules, taxonomy",
    links: [
      { to: "/datasets", label: "Datasets" },
      { to: "/rules", label: "Rules" },
      { to: "/rules/queue", label: "Rule review queue" },
      { to: "/agents", label: "Agents" },
      { to: "/models", label: "Models" },
      { to: "/skills", label: "Skills" },
      { to: "/playground", label: "Playground" },
    ],
  },
];

export function NavSidebar() {
  return (
    <aside
      className="border-r border-bny-mist bg-white sticky top-0 h-screen px-4 py-5 overflow-y-auto"
      aria-label="primary"
    >
      <div className="flex items-center gap-2 px-2 py-1 mb-5">
        <span className="inline-flex items-center justify-center w-8 h-8 rounded-md bg-bny-ink text-white text-xs font-semibold">
          AS
        </span>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-bny-fog leading-none">
            BNY
          </div>
          <div className="text-sm font-semibold leading-tight">Asset Servicing</div>
        </div>
      </div>
      <nav className="flex flex-col gap-1">
        {SECTIONS.map((section) => (
          <div key={section.title} className="mb-3">
            <div className="text-[10px] uppercase tracking-wider text-bny-fog mt-2 mb-1 px-2 font-semibold">
              {section.title}
            </div>
            {section.caption && (
              <div className="text-[10px] text-bny-fog px-2 mb-1.5 leading-tight">
                {section.caption}
              </div>
            )}
            {section.links.map((l) => (
              <Link
                key={l.label}
                to={l.to}
                params={l.params}
                className="block text-[13px] px-2 py-1.5 rounded-md text-bny-slate hover:bg-bny-paper [&.active]:bg-bny-tealLight [&.active]:text-bny-ink [&.active]:font-medium"
                activeOptions={{ exact: l.to === "/" }}
                activeProps={{ className: "active" }}
              >
                <span>{l.label}</span>
                {l.hint && (
                  <span className="block text-[10px] text-bny-fog leading-tight">
                    {l.hint}
                  </span>
                )}
              </Link>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
