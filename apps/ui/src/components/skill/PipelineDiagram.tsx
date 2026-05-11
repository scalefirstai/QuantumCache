import type {
  PipelineCacheNote,
  PipelineEdge,
  PipelineNode,
} from "@/types/skill";

const variantStroke: Record<PipelineNode["variant"], string> = {
  input: "#04243C",
  step: "#2B9CAE",
  filter: "#BA7517",
  merge: "#2B9CAE",
  output: "#04243C",
};

const variantFill: Record<PipelineNode["variant"], string> = {
  input: "#FFFFFF",
  step: "#FFFFFF",
  filter: "#FFFFFF",
  merge: "#DDF1F4",
  output: "#04243C",
};

interface Props {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  cache: PipelineCacheNote;
}

export function PipelineDiagram({ nodes, edges, cache }: Props) {
  const byId = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg
      width="100%"
      viewBox="0 0 680 360"
      role="img"
      aria-label="Internal pipeline of the Retrieval.hybrid skill"
      data-testid="pipeline-diagram"
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>Internal pipeline of the Retrieval.hybrid skill</title>
      <desc>
        Query enters at left, splits into BM25 lexical retrieval over OpenSearch
        and dense retrieval over Qdrant. Both produce top 100 candidates that
        union to about 150, get filtered by entity and product scoping, then
        reranked by Cohere into top 20 results.
      </desc>
      <defs>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path
            d="M2 1L8 5L2 9"
            fill="none"
            stroke="context-stroke"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </marker>
      </defs>

      {edges.map((e, i) => {
        const from = byId.get(e.from);
        const to = byId.get(e.to);
        if (!from || !to) return null;
        const x1 = from.x + from.w / 2;
        const y1 = from.y + from.h / 2;
        const x2 = to.x + to.w / 2;
        const y2 = to.y + to.h / 2;
        const stroke = e.kind === "main" ? "#04243C" : "#7B8E9D";
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke={stroke}
            strokeWidth="0.5"
            markerEnd="url(#arrow)"
          />
        );
      })}

      {nodes.map((n) => (
        <g key={n.id} data-stage-id={n.id}>
          <rect
            x={n.x}
            y={n.y}
            width={n.w}
            height={n.h}
            rx={8}
            fill={variantFill[n.variant]}
            stroke={n.variant === "output" ? "none" : variantStroke[n.variant]}
            strokeWidth="0.5"
          />
          <text
            x={n.x + n.w / 2}
            y={n.y + 22}
            textAnchor="middle"
            fontSize="13"
            fontWeight="500"
            fill={n.variant === "output" ? "#FFFFFF" : "#04243C"}
          >
            {n.label}
          </text>
          {n.sub && (
            <text
              x={n.x + n.w / 2}
              y={n.y + 38}
              textAnchor="middle"
              fontSize="11"
              fill={n.variant === "output" ? "#7FCAD5" : "#4A6478"}
            >
              {n.sub}
            </text>
          )}
          {n.meta && (
            <text
              x={n.x + n.w / 2}
              y={n.y + 53}
              textAnchor="middle"
              fontSize="11"
              fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
              fill={n.variant === "output" ? "#7FCAD5" : "#7B8E9D"}
            >
              {n.meta}
            </text>
          )}
        </g>
      ))}

      <g data-testid="pipeline-cache-callout">
        <rect
          x={22}
          y={170}
          width={320}
          height={178}
          rx={8}
          fill="none"
          stroke="#BFD9E4"
          strokeWidth="0.5"
          strokeDasharray="4 3"
        />
        <text x={36} y={190} fontSize="11" fontWeight="500" fill="#7B8E9D">
          {cache.title}
        </text>
        {cache.lines.map((l, i) => (
          <text
            key={i}
            x={36}
            y={208 + i * 16}
            fontSize="11"
            fill="#4A6478"
          >
            {l}
          </text>
        ))}
        <text x={36} y={266} fontSize="11" fontWeight="500" fill="#7B8E9D">
          HIT RATE · {cache.hitRate} (last 30 days)
        </text>
        <text
          x={36}
          y={326}
          fontSize="11"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fill="#7B8E9D"
        >
          P95 cached · {cache.cachedP95}
        </text>
      </g>
    </svg>
  );
}
