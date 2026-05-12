import { useEffect, useState } from "react";
import { listModels } from "@/api/agents";
import type { Model } from "@/types/agent";

export function ModelsRoute() {
  const [models, setModels] = useState<Model[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    listModels().then(setModels).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <ErrorBox msg={err} />;
  if (!models) return <div className="px-6 py-5 text-sm text-bny-fog">Loading…</div>;

  return (
    <div className="px-6 py-5" data-testid="models-root">
      <header className="mb-4">
        <h1 className="text-xl font-semibold leading-tight">Models</h1>
        <p className="text-sm text-bny-fog mt-1">
          Anthropic tiers wired into the orchestrator's tier dispatch.
        </p>
      </header>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {models.map((m) => (
          <article
            key={m.id}
            className="border border-bny-mist rounded-lg bg-white p-4"
            data-testid={`model-card-${m.id}`}
          >
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-sm font-semibold">{m.displayName}</h2>
              <span className="text-[11px] px-1.5 py-0.5 rounded uppercase bg-bny-tealLight text-bny-ink">
                {m.tier}
              </span>
            </div>
            <p className="text-xs text-bny-fog font-mono mb-2">{m.id}</p>
            <dl className="text-xs grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
              <dt className="text-bny-fog">Provider</dt>
              <dd>{m.provider}</dd>
              <dt className="text-bny-fog">Context</dt>
              <dd className="font-mono">{m.contextWindow.toLocaleString()} tok</dd>
              <dt className="text-bny-fog">Input $/MTok</dt>
              <dd className="font-mono">${m.pricing.inputPerMTok.toFixed(2)}</dd>
              <dt className="text-bny-fog">Output $/MTok</dt>
              <dd className="font-mono">${m.pricing.outputPerMTok.toFixed(2)}</dd>
              <dt className="text-bny-fog">Tools</dt>
              <dd>{m.supportsTools ? "yes" : "no"}</dd>
              <dt className="text-bny-fog">Thinking</dt>
              <dd>{m.supportsThinking ? "yes" : "no"}</dd>
            </dl>
            <p className="mt-3 text-xs text-bny-slate border-t border-bny-mist pt-2">{m.notes}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

const ErrorBox = ({ msg }: { msg: string }) => (
  <div className="px-6 py-5 max-w-xl">
    <pre className="text-xs">{msg}</pre>
  </div>
);
