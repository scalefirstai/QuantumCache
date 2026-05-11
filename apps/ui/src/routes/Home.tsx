import { Link, type LinkProps } from "@tanstack/react-router";

type Card = { title: string; sub: string } & Pick<
  LinkProps,
  "to" | "params"
>;

const cards: Card[] = [
  {
    to: "/pipeline/$ddqId",
    params: { ddqId: "ddq_8db64d9cb6c5" },
    title: "Pipeline · email → 8-agent → sealed",
    sub: "Acme Pension Q2 2026 · 5 questions · live data through QuestionMapper, EvidenceSourcer, DraftComposer, CitationVerifier, ConsistencyChecker, PiiScrubber, FreshnessAuditor, ApprovalRouter",
  },
  {
    to: "/runs/$runId",
    params: { runId: "run_20260510T125906_2b46b0fd" },
    title: "Run walkthrough",
    sub: "5 sealed runs · AFME · CAIQ · ESG · adversarial · 7-stage view",
  },
  {
    to: "/employees/$de",
    params: { de: "aria" },
    title: "Aria · DDQ specialist",
    sub: "Live console — KPIs, agent roster, human queue",
  },
  {
    to: "/employees/$de/review/$period",
    params: { de: "aria", period: "q1-2026" },
    title: "Aria · Q1 performance review",
    sub: "Nov 2025 – Apr 2026 · 847 questions · 23 DDQs",
  },
  {
    to: "/skills/$skillId",
    params: { skillId: "retrieval-hybrid" },
    title: "Retrieval.hybrid",
    sub: "Skill spec · BM25 + dense + Cohere rerank",
  },
];

export function HomeRoute() {
  return (
    <div>
      <h1 className="text-xl font-medium mb-1">BNY DDQ console</h1>
      <p className="text-sm text-bny-slate mb-6">
        Operator-facing views over the Aria DDQ digital employee.
      </p>
      <div className="grid grid-cols-2 gap-3 max-w-3xl">
        {cards.map((c) => (
          <Link
            key={c.title}
            to={c.to}
            params={c.params}
            className="block bg-white border border-bny-mist rounded-lg p-4 hover:border-bny-teal transition-colors"
          >
            <div className="font-medium text-sm">{c.title}</div>
            <div className="text-xs text-bny-slate mt-1">{c.sub}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
