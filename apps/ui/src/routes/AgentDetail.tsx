import { useParams } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import {
  activateVersion,
  applyTemplate,
  createVersion,
  getAgent,
  getAudit,
  listModels,
  listTemplates,
  listVersions,
} from "@/api/agents";
import type {
  AgentDetail,
  AuditEntry,
  Model,
  Template,
  VersionSummary,
} from "@/types/agent";

type Tab = "config" | "versions" | "history";

export function AgentDetailRoute() {
  const { agentId } = useParams({ strict: false }) as { agentId: string };
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [tab, setTab] = useState<Tab>("config");
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const a = await getAgent(agentId);
      setAgent(a);
      if (a.kind === "llm") {
        setVersions(await listVersions(agentId));
        setAudit(await getAudit(agentId));
      }
    } catch (e) {
      setErr(String(e));
    }
  }, [agentId]);

  useEffect(() => {
    listModels().then(setModels).catch(() => {});
    listTemplates().then(setTemplates).catch(() => {});
    void reload();
  }, [reload]);

  if (err && !agent) return <ErrorBox msg={err} />;
  if (!agent) return <div className="px-6 py-5 text-sm text-bny-fog">Loading…</div>;

  return (
    <div className="px-6 py-5 max-w-5xl" data-testid="agent-detail-root">
      <header className="mb-4">
        <div className="flex items-center gap-2 mb-1">
          <h1 className="text-xl font-semibold leading-tight">{agent.name}</h1>
          <span
            className={
              "text-[11px] px-1.5 py-0.5 rounded uppercase tracking-wide " +
              (agent.kind === "llm" ? "bg-bny-tealLight text-bny-ink" : "bg-bny-mist text-bny-slate")
            }
          >
            {agent.kind}
          </span>
          {agent.activeVersion && (
            <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-bny-paper border border-bny-mist text-bny-slate">
              v{agent.activeVersion} active
            </span>
          )}
        </div>
        <p className="text-sm text-bny-fog">{agent.description}</p>
      </header>

      {agent.kind === "rule" ? (
        <div className="border border-bny-mist rounded-lg bg-white p-4 text-sm">
          This agent has no editable prompt — its logic lives in{" "}
          <code className="text-xs">services/{agent.id}/agent.py</code>.
        </div>
      ) : (
        <>
          <nav className="border-b border-bny-mist mb-4 flex gap-3 text-sm" data-testid="agent-tabs">
            {(["config", "versions", "history"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                data-testid={`tab-${t}`}
                className={
                  "px-3 py-1.5 -mb-px border-b-2 capitalize " +
                  (tab === t
                    ? "border-bny-teal text-bny-ink font-medium"
                    : "border-transparent text-bny-fog hover:text-bny-ink")
                }
              >
                {t}
              </button>
            ))}
          </nav>

          {tab === "config" && (
            <ConfigTab
              agent={agent}
              models={models}
              templates={templates}
              onSaved={reload}
            />
          )}
          {tab === "versions" && (
            <VersionsTab agentId={agent.id} versions={versions} onActivated={reload} />
          )}
          {tab === "history" && <HistoryTab audit={audit} />}
        </>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────

function ConfigTab({
  agent,
  models,
  templates,
  onSaved,
}: {
  agent: AgentDetail;
  models: Model[];
  templates: Template[];
  onSaved: () => void;
}) {
  const active = agent.active!;
  const [system, setSystem] = useState(active.system);
  const [userTpl, setUserTpl] = useState(active.userTemplate);
  const [model, setModel] = useState(active.model);
  const [temperature, setTemperature] = useState(active.temperature);
  const [maxTokens, setMaxTokens] = useState(active.maxTokens);
  const [tools, setTools] = useState<string[]>(active.tools);
  const [bump, setBump] = useState<"patch" | "minor" | "major">("patch");
  const [comment, setComment] = useState("");
  const [actor, setActor] = useState("aria@bny.com");
  const [activate, setActivate] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  // Reset form when underlying active version changes (e.g., after save).
  useEffect(() => {
    setSystem(active.system);
    setUserTpl(active.userTemplate);
    setModel(active.model);
    setTemperature(active.temperature);
    setMaxTokens(active.maxTokens);
    setTools(active.tools);
  }, [active.sha256, active.system, active.userTemplate, active.model,
      active.temperature, active.maxTokens, active.tools]);

  const onSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const doc = await createVersion(agent.id, {
        baseVersion: active.version,
        bump,
        system,
        userTemplate: userTpl,
        model,
        temperature,
        maxTokens,
        tools,
        comment: comment || null,
        actor,
        activate,
      } as never);
      setStatus(`Saved v${doc.version}${activate ? " · activated" : ""}.`);
      setComment("");
      onSaved();
    } catch (e) {
      setStatus(`Failed: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const onApplyTemplate = async (templateId: string) => {
    setSaving(true);
    setStatus(null);
    try {
      const doc = await applyTemplate(agent.id, { templateId, actor });
      setStatus(`Applied template "${templateId}" → v${doc.version}.`);
      onSaved();
    } catch (e) {
      setStatus(`Failed: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-2 space-y-4">
        <Section title="System prompt" testid="system-prompt">
          <textarea
            data-testid="system-textarea"
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            className="w-full h-72 text-xs font-mono p-3 rounded-md border border-bny-mist focus:outline-none focus:border-bny-teal"
          />
        </Section>
        <Section title="User template" testid="user-template">
          <textarea
            data-testid="user-template-textarea"
            value={userTpl}
            onChange={(e) => setUserTpl(e.target.value)}
            className="w-full h-40 text-xs font-mono p-3 rounded-md border border-bny-mist focus:outline-none focus:border-bny-teal"
          />
        </Section>
      </div>

      <div className="space-y-4">
        <Section title="Model & parameters">
          <label className="block text-xs text-bny-fog mb-1">Model</label>
          <select
            data-testid="model-select"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="w-full text-sm p-2 rounded-md border border-bny-mist mb-2"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.displayName} ({m.tier})
              </option>
            ))}
          </select>
          <label className="block text-xs text-bny-fog mb-1">
            Temperature: <span className="font-mono">{temperature.toFixed(2)}</span>
          </label>
          <input
            data-testid="temperature-slider"
            type="range" min="0" max="1" step="0.05"
            value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            className="w-full mb-2"
          />
          <label className="block text-xs text-bny-fog mb-1">Max tokens</label>
          <input
            data-testid="max-tokens-input"
            type="number" min="64" max="200000"
            value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 0)}
            className="w-full text-sm p-2 rounded-md border border-bny-mist"
          />
        </Section>

        <Section title="Tools">
          <ul className="text-xs space-y-1 font-mono">
            {tools.map((t, idx) => (
              <li
                key={t}
                className="flex items-center justify-between px-2 py-1 rounded bg-bny-paper border border-bny-mist"
              >
                {t}
                <button
                  className="text-bny-fog hover:text-bny-ink"
                  onClick={() => setTools(tools.filter((_, i) => i !== idx))}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Save as new version">
          <label className="block text-xs text-bny-fog mb-1">Bump</label>
          <select
            data-testid="bump-select"
            value={bump}
            onChange={(e) => setBump(e.target.value as "patch" | "minor" | "major")}
            className="w-full text-sm p-2 rounded-md border border-bny-mist mb-2"
          >
            <option value="patch">patch</option>
            <option value="minor">minor</option>
            <option value="major">major</option>
          </select>
          <label className="block text-xs text-bny-fog mb-1">Comment</label>
          <input
            data-testid="comment-input"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Why this change?"
            className="w-full text-sm p-2 rounded-md border border-bny-mist mb-2"
          />
          <label className="block text-xs text-bny-fog mb-1">Actor</label>
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            className="w-full text-sm p-2 rounded-md border border-bny-mist mb-2"
          />
          <label className="flex items-center gap-2 text-xs mb-3">
            <input
              data-testid="activate-checkbox"
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
            />
            Activate immediately
          </label>
          <button
            onClick={onSave}
            disabled={saving}
            data-testid="save-button"
            className="w-full text-sm font-medium px-3 py-2 rounded-md bg-bny-teal text-white hover:bg-bny-teal/90 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
          {status && (
            <p data-testid="save-status" className="text-xs mt-2 text-bny-fog">
              {status}
            </p>
          )}
        </Section>

        {templates.length > 0 && (
          <Section title="Apply template">
            <div className="space-y-2">
              {templates.map((t) => (
                <div
                  key={t.id}
                  className="border border-bny-mist rounded-md p-2 text-xs"
                  data-testid={`template-${t.id}`}
                >
                  <div className="font-medium">{t.name}</div>
                  <p className="text-bny-fog mt-0.5">{t.description}</p>
                  <button
                    onClick={() => onApplyTemplate(t.id)}
                    disabled={saving}
                    className="mt-2 text-[11px] px-2 py-1 rounded bg-bny-paper border border-bny-mist hover:bg-white"
                  >
                    Apply
                  </button>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

function VersionsTab({
  agentId,
  versions,
  onActivated,
}: {
  agentId: string;
  versions: VersionSummary[];
  onActivated: () => void;
}) {
  const onActivate = async (v: string) => {
    await activateVersion(agentId, { version: v, actor: "aria@bny.com" });
    onActivated();
  };
  return (
    <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
      <table className="w-full text-sm" data-testid="versions-table">
        <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
          <tr>
            <Th>Version</Th>
            <Th>Created</Th>
            <Th>SHA256</Th>
            <Th>Comment</Th>
            <Th>Status</Th>
            <Th></Th>
          </tr>
        </thead>
        <tbody>
          {versions.map((v) => (
            <tr
              key={v.version}
              className="border-t border-bny-mist"
              data-testid={`version-row-${v.version}`}
            >
              <Td className="font-mono">{v.version}</Td>
              <Td className="text-xs text-bny-fog">
                {new Date(v.createdAt).toLocaleString()}
              </Td>
              <Td className="text-xs font-mono text-bny-fog">
                {v.sha256.replace(/^sha256:/, "").slice(0, 12)}
              </Td>
              <Td className="text-xs">{v.comment ?? "—"}</Td>
              <Td>
                {v.isActive ? (
                  <span className="text-[11px] px-1.5 py-0.5 rounded uppercase bg-bny-tealLight text-bny-ink">
                    active
                  </span>
                ) : (
                  <span className="text-[11px] text-bny-fog">—</span>
                )}
              </Td>
              <Td>
                {!v.isActive && (
                  <button
                    onClick={() => onActivate(v.version)}
                    data-testid={`activate-${v.version}`}
                    className="text-[11px] px-2 py-1 rounded bg-bny-paper border border-bny-mist hover:bg-white"
                  >
                    Activate
                  </button>
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryTab({ audit }: { audit: AuditEntry[] }) {
  if (audit.length === 0)
    return (
      <p className="text-sm text-bny-fog" data-testid="audit-empty">
        No edits yet.
      </p>
    );
  return (
    <ol className="space-y-2" data-testid="audit-log">
      {audit.map((e, i) => (
        <li
          key={i}
          className="border border-bny-mist rounded-md p-3 text-sm bg-white"
          data-testid={`audit-${e.action}-${e.toVersion}`}
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium">
              <code className="text-xs px-1 py-0.5 rounded bg-bny-paper">{e.action}</code>{" "}
              {e.fromVersion ? `${e.fromVersion} → ` : ""}
              <span className="font-mono">v{e.toVersion}</span>
            </span>
            <span className="text-xs text-bny-fog">{new Date(e.ts).toLocaleString()}</span>
          </div>
          <p className="text-xs text-bny-fog">
            actor: {e.actor}
            {e.comment ? ` · ${e.comment}` : ""}
          </p>
        </li>
      ))}
    </ol>
  );
}

const Section = ({
  title, children, testid,
}: { title: string; children: React.ReactNode; testid?: string }) => (
  <div className="border border-bny-mist rounded-lg bg-white" data-testid={testid}>
    <div className="px-3 py-2 border-b border-bny-mist text-xs uppercase tracking-wide text-bny-fog">
      {title}
    </div>
    <div className="p-3">{children}</div>
  </div>
);

const Th = ({ children = null }: { children?: React.ReactNode }) => (
  <th className="text-left font-medium px-3 py-2">{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
);
const ErrorBox = ({ msg }: { msg: string }) => (
  <div className="px-6 py-5 max-w-xl">
    <div className="border border-bny-mist rounded-lg bg-white p-4 text-sm">
      <div className="font-medium mb-1">Failed to load.</div>
      <pre className="text-xs text-bny-fog whitespace-pre-wrap">{msg}</pre>
    </div>
  </div>
);
