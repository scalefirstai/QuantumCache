import { useMemo, useState } from "react";
import type { PipelineQuestion, PipelineStage } from "@/types/pipeline";
import { StageStatusDot } from "./StageStatusDot";

function shortHash(h: string | undefined | null, n = 14): string {
  if (!h) return "—";
  return h.split(":").pop()!.slice(0, n);
}

// Highlight `[span:<id>]` markers inside draft text so reviewers can see
// citations at a glance.
function renderDraftWithCitations(text: string) {
  const parts = text.split(/(\[span:[^\]]+\])/g);
  return parts.map((p, i) => {
    if (p.startsWith("[span:")) {
      return (
        <mark
          key={i}
          className="bg-bny-tealLight text-bny-ink font-mono text-[11px] rounded px-1 py-0.5 mx-0.5"
        >
          {p}
        </mark>
      );
    }
    return <span key={i}>{p}</span>;
  });
}

function JsonBlock({ value }: { value: unknown }) {
  const json = JSON.stringify(value, null, 2);
  return (
    <pre className="text-[11px] leading-[1.55] font-mono whitespace-pre-wrap break-words bg-bny-paper border border-bny-mist rounded-md p-3 text-bny-ink max-h-[260px] overflow-auto">
      {json}
    </pre>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2 text-[12px]">
      <span className="text-bny-fog uppercase tracking-wider text-[10px] font-medium min-w-[120px]">
        {label}
      </span>
      <span className="text-bny-ink break-all">{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white border border-bny-mist rounded-md p-3">
      <h3 className="text-[11px] uppercase tracking-wider text-bny-fog font-medium m-0 mb-2">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

interface Props {
  question: PipelineQuestion;
  stage: PipelineStage;
}

export function DataInspector({ question, stage }: Props) {
  const [tab, setTab] = useState<"data" | "events" | "raw">("data");

  const payload = stage.payload as Record<string, unknown>;
  const tokens = payload.tokens as
    | { input?: number; output?: number; cache_read?: number }
    | undefined;

  const stageContent = useMemo(() => {
    switch (stage.id) {
      case "intake": {
        const q = payload.question as Record<string, unknown> | undefined;
        return (
          <Section title="Inbound question">
            <KV label="question_id" value={<span className="font-mono">{String(q?.question_id ?? "—")}</span>} />
            <KV label="framework" value={String(q?.framework ?? "—")} />
            <KV label="taxonomy" value={<span className="font-mono">{String(payload.taxonomyVersion ?? "—")}</span>} />
            <KV label="library" value={<span className="font-mono">{String(payload.libraryVersion ?? "—")}</span>} />
            <KV label="platform" value={<span className="font-mono">{String(payload.platformVersion ?? "—")}</span>} />
            <div className="bg-bny-paper border border-bny-mist rounded-md p-3 text-[13px] leading-[1.6] text-bny-ink mt-1">
              {String(q?.text ?? "—")}
            </div>
          </Section>
        );
      }
      case "mapper": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        return (
          <>
            <Section title="Input — what Claude saw">
              <KV label="framework" value={String(input.framework ?? "—")} />
              <KV label="candidates" value={String(input.candidateCount ?? 0)} />
              <KV label="model tier" value={<span className="font-mono">{String(input.modelTier ?? "—")}</span>} />
              <KV label="prompt hash" value={<span className="font-mono">{shortHash(input.promptHash as string)}</span>} />
            </Section>
            <Section title="Output — Claude's classification">
              <KV
                label="canonical_id"
                value={
                  <span className="font-mono">{(output.canonicalId as string) ?? "(unclassified)"}</span>
                }
              />
              <KV
                label="confidence"
                value={
                  <span className="font-mono">
                    {Number(output.confidence ?? 0).toFixed(3)}
                  </span>
                }
              />
              <KV
                label="routed to SME"
                value={output.routedToSme ? "yes" : "no"}
              />
            </Section>
          </>
        );
      }
      case "library": {
        return (
          <Section title="Library lookup">
            <KV
              label="canonical_id"
              value={<span className="font-mono">{(payload.canonicalId as string) ?? "(none)"}</span>}
            />
            <KV label="entity" value={String(payload.entity ?? "—")} />
            <KV label="product" value={String(payload.product ?? "(any)")} />
            <KV
              label="hit"
              value={
                payload.hit ? (
                  <span className="text-bny-ok font-medium">library hit</span>
                ) : (
                  <span className="text-bny-fog">library miss</span>
                )
              }
            />
            {payload.entryId ? (
              <KV
                label="entry_id"
                value={<span className="font-mono">{String(payload.entryId)}</span>}
              />
            ) : null}
          </Section>
        );
      }
      case "retrieve": {
        return (
          <Section title="Hybrid retrieval (BM25 + dense + RRF)">
            <KV label="k" value={String(payload.k ?? "—")} />
            <KV label="returned spans" value={String(payload.returned ?? 0)} />
            <KV
              label="top RRF score"
              value={
                <span className="font-mono">
                  {Number(payload.topScore ?? 0).toFixed(4)}
                </span>
              }
            />
            <KV
              label="top sources"
              value={
                Array.isArray(payload.topSources)
                  ? (payload.topSources as string[]).join(", ")
                  : "—"
              }
            />
            <KV
              label="filters"
              value={
                <span className="font-mono text-[11px]">
                  {JSON.stringify(payload.filters ?? {})}
                </span>
              }
            />
          </Section>
        );
      }
      case "sourcer": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        const ids = (output.selectedSpanIds ?? []) as string[];
        return (
          <>
            <Section title="Input">
              <KV label="candidates" value={String(input.candidateCount ?? 0)} />
              <KV
                label="library context"
                value={input.libraryHit ? "yes" : "no"}
              />
            </Section>
            <Section title="Output — curated bundle">
              <KV
                label="selected"
                value={`${ids.length} span${ids.length === 1 ? "" : "s"}`}
              />
              <KV
                label="sufficient"
                value={
                  output.sufficient ? (
                    <span className="text-bny-ok font-medium">yes</span>
                  ) : (
                    <span className="text-bny-ochre font-medium">no</span>
                  )
                }
              />
              {ids.length > 0 && (
                <ul className="mt-1 space-y-1">
                  {ids.map((id) => (
                    <li
                      key={id}
                      className="text-[11px] font-mono text-bny-slate break-all"
                    >
                      • {id}
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </>
        );
      }
      case "drafter": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        const draftText = (payload.draftText as string) ?? "";
        const skip = payload.skip as Record<string, unknown> | null;
        return (
          <>
            <Section title="Input">
              <KV
                label="tier"
                value={<span className="font-mono">{String(input.tier ?? "—")}</span>}
              />
              <KV
                label="evidence spans"
                value={String(input.evidenceCount ?? 0)}
              />
              <KV
                label="library entry"
                value={input.usedLibraryEntry ? "in context" : "—"}
              />
            </Section>
            <Section title="Output">
              {skip ? (
                <p className="text-[13px] text-bny-ochre">
                  Drafter skipped: {String(skip.reason ?? "no evidence")}
                </p>
              ) : (
                <>
                  <KV
                    label="tier used"
                    value={
                      <span className="font-mono">{String(output.tierUsed ?? "—")}</span>
                    }
                  />
                  <KV label="characters" value={String(output.draftChars ?? 0)} />
                  <KV label="citations" value={String(output.citationCount ?? 0)} />
                  <div className="bg-bny-paper border border-bny-mist rounded-md p-3 text-[13px] leading-[1.65] text-bny-ink whitespace-pre-wrap max-h-[260px] overflow-auto">
                    {draftText ? renderDraftWithCitations(draftText) : "(empty)"}
                  </div>
                </>
              )}
            </Section>
          </>
        );
      }
      case "verifier": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        return (
          <Section title="Citation verification (deterministic + Haiku)">
            <KV
              label="citations checked"
              value={String(output.checked ?? input.citationCount ?? 0)}
            />
            <KV
              label="unresolved"
              value={String(output.unresolved ?? 0)}
            />
            <KV
              label="unsupported"
              value={String(output.unsupported ?? 0)}
            />
            <KV
              label="all pass"
              value={
                output.allPass ? (
                  <span className="text-bny-ok font-medium">yes</span>
                ) : (
                  <span className="text-bny-danger font-medium">no</span>
                )
              }
            />
          </Section>
        );
      }
      case "consistency": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        return (
          <Section title="Cross-DDQ consistency">
            <KV
              label="prior responses"
              value={String(input.priorCount ?? 0)}
            />
            <KV
              label="consistent"
              value={
                output.consistent ? (
                  <span className="text-bny-ok font-medium">yes</span>
                ) : (
                  <span className="text-bny-ochre font-medium">drift</span>
                )
              }
            />
            <KV
              label="drift detected"
              value={output.driftDetected ? "yes" : "no"}
            />
            {output.reason ? (
              <p className="text-[12px] text-bny-slate mt-1">
                {String(output.reason)}
              </p>
            ) : null}
          </Section>
        );
      }
      case "pii": {
        const input = (payload.input ?? {}) as Record<string, unknown>;
        const output = (payload.output ?? {}) as Record<string, unknown>;
        return (
          <Section title="PII scrub (regex + Haiku contextual)">
            <KV label="input chars" value={String(input.inputChars ?? 0)} />
            <KV
              label="regex findings"
              value={String(input.regexFindings ?? 0)}
            />
            <KV
              label="LLM findings"
              value={String(output.llmFindings ?? 0)}
            />
            <KV
              label="total findings"
              value={String(output.findingsTotal ?? 0)}
            />
            <KV
              label="halt"
              value={
                output.halt ? (
                  <span className="text-bny-danger font-medium">yes</span>
                ) : (
                  <span className="text-bny-ok font-medium">no</span>
                )
              }
            />
          </Section>
        );
      }
      case "freshness": {
        const reasons = (payload.reasons ?? []) as string[];
        return (
          <Section title="Freshness audit (rule-based)">
            <KV
              label="stale"
              value={
                payload.stale ? (
                  <span className="text-bny-ochre font-medium">yes</span>
                ) : (
                  <span className="text-bny-ok font-medium">no</span>
                )
              }
            />
            <KV
              label="today"
              value={<span className="font-mono">{String(payload.today ?? "—")}</span>}
            />
            {payload.oldestEvidenceDate ? (
              <KV
                label="oldest evidence"
                value={<span className="font-mono">{String(payload.oldestEvidenceDate)}</span>}
              />
            ) : null}
            {reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {reasons.map((r, i) => (
                  <li
                    key={i}
                    className="text-[12px] text-bny-ochre leading-snug"
                  >
                    • {r}
                  </li>
                ))}
              </ul>
            )}
          </Section>
        );
      }
      case "router": {
        const agg = (payload.aggregate ?? {}) as Record<string, unknown>;
        return (
          <>
            <Section title="Aggregate validation">
              <KV label="verdict" value={String(agg.verdict ?? "—")} />
              <KV
                label="verifier all_pass"
                value={agg.verifier_all_pass ? "yes" : "no"}
              />
              <KV label="pii halt" value={agg.pii_halt ? "yes" : "no"} />
              <KV
                label="consistency drift"
                value={agg.consistency_drift ? "yes" : "no"}
              />
              <KV
                label="freshness stale"
                value={agg.freshness_stale ? "yes" : "no"}
              />
              <KV label="draft chars" value={String(agg.draft_chars ?? 0)} />
            </Section>
            <Section title="Routing decision">
              <KV
                label="route"
                value={
                  <span className="font-mono">{String(payload.route ?? "—")}</span>
                }
              />
              <KV
                label="queue"
                value={<span className="font-mono">{String(payload.queue ?? "—")}</span>}
              />
              <KV label="tier" value={<span className="font-mono">{String(payload.tier ?? "—")}</span>} />
              {payload.rationale ? (
                <p className="text-[12px] text-bny-slate mt-1">
                  {String(payload.rationale)}
                </p>
              ) : null}
            </Section>
          </>
        );
      }
      case "sealed": {
        return (
          <Section title="L01 seal — audit journal closed">
            <KV
              label="merkle_root"
              value={<span className="font-mono">{shortHash(payload.merkleRoot as string, 24)}</span>}
            />
            <KV
              label="response_hash"
              value={<span className="font-mono">{shortHash(payload.outboundResponseHash as string, 24)}</span>}
            />
            <KV label="verdict" value={String(payload.verdict ?? "—")} />
            <KV label="route" value={String(payload.route ?? "—")} />
            <KV
              label="sealed_at"
              value={String(payload.sealedAt ?? "—")}
            />
            <div className="bg-bny-paper border border-bny-mist rounded-md p-3 text-[13px] leading-[1.65] text-bny-ink whitespace-pre-wrap max-h-[260px] overflow-auto">
              {payload.outboundResponse
                ? renderDraftWithCitations(payload.outboundResponse as string)
                : "(no outbound text)"}
            </div>
          </Section>
        );
      }
      default:
        return <JsonBlock value={payload} />;
    }
  }, [payload, stage.id]);

  return (
    <div
      data-testid="pipeline-data-inspector"
      className="bg-bny-paper border border-bny-mist rounded-lg p-4 h-full overflow-auto"
    >
      <header className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <StageStatusDot status={stage.status} />
            <h2 className="text-base font-medium m-0">
              {stage.title}
            </h2>
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-px rounded font-medium bg-white text-bny-slate border border-bny-mist">
              {stage.kind}
            </span>
          </div>
          <p className="text-[12px] text-bny-slate m-0 mt-0.5">
            <span className="font-mono">{stage.agent}</span> · {stage.summary}
          </p>
        </div>
        <div className="text-right text-[11px] text-bny-fog leading-tight shrink-0">
          <div>
            Q{question.questionId} · {question.framework}
          </div>
          <div>
            <span className="font-mono">{shortHash(question.runId, 20)}</span>
          </div>
          {tokens ? (
            <div>
              tokens: in {tokens.input ?? 0}/out {tokens.output ?? 0}
              {tokens.cache_read ? ` (cache ${tokens.cache_read})` : ""}
            </div>
          ) : null}
        </div>
      </header>

      <div role="tablist" aria-label="Inspector view" className="flex gap-1 mb-3">
        {(["data", "events", "raw"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            data-tab={t}
            onClick={() => setTab(t)}
            className={[
              "text-[11px] px-2.5 py-1 rounded-md border transition-colors",
              tab === t
                ? "bg-bny-tealLight border-bny-teal text-bny-ink"
                : "bg-white border-bny-mist text-bny-slate hover:border-bny-teal",
            ].join(" ")}
          >
            {t === "data" ? "Stage data" : t === "events" ? `Journal events (${stage.events.length})` : "Raw payload"}
          </button>
        ))}
      </div>

      {tab === "data" && <div className="space-y-3">{stageContent}</div>}
      {tab === "events" && (
        <div className="space-y-2">
          {stage.events.length === 0 ? (
            <p className="text-[12px] text-bny-fog">
              No journal events were emitted for this stage on this run.
            </p>
          ) : (
            stage.events.map((e) => (
              <div
                key={e.eventId}
                className="bg-white border border-bny-mist rounded-md p-3"
              >
                <div className="flex items-baseline justify-between gap-2 mb-1">
                  <span className="text-[12px] font-medium text-bny-ink">
                    {e.kind}
                  </span>
                  <span className="text-[10px] text-bny-fog font-mono">
                    {e.ts.slice(11, 19)}Z
                  </span>
                </div>
                <div className="text-[10px] text-bny-fog mb-1 font-mono break-all">
                  {e.eventId} · payload {shortHash(e.payloadHash)} · chain{" "}
                  {shortHash(e.chainHash)}
                </div>
                <JsonBlock value={e.payload} />
              </div>
            ))
          )}
        </div>
      )}
      {tab === "raw" && <JsonBlock value={payload} />}
    </div>
  );
}
