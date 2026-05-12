import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { createRule, deleteRule, listRules } from "@/api/rules";
import type { RuleSummary } from "@/types/rule";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  FilterRow,
  Modal,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Input,
  TagPill,
} from "@/components/datasets/Common";
import { RuleEditor } from "@/components/rules/RuleEditor";
import {
  blankRuleEditor,
  type RuleEditorValue,
} from "@/components/rules/ruleEditorValue";
import { StatusBadge } from "@/components/rules/StatusBadge";

export function RulesListRoute() {
  const [items, setItems] = useState<RuleSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [engineFilter, setEngineFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = () =>
    listRules({}).then(setItems).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
  }, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.toLowerCase();
    return items.filter((r) => {
      if (engineFilter && r.engine !== engineFilter) return false;
      if (statusFilter && r.status !== statusFilter) return false;
      if (!q) return true;
      return (
        r.ruleId.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q)
      );
    });
  }, [items, query, engineFilter, statusFilter]);

  if (err) return <ErrorBox title="Failed to load rules" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="rules-list-root">
      <PageHeader
        eyebrow="Rule engine"
        title="Rules"
        subtitle="Configure FreshnessAuditor and ApprovalRouter rules. Edits flow draft → pending review → active."
        actions={
          <>
            <Link to="/rules/queue" className="text-sm text-bny-teal hover:underline" data-testid="goto-queue">
              SME queue →
            </Link>
            <PrimaryButton onClick={() => setModalOpen(true)} testId="create-rule-btn">
              + New rule
            </PrimaryButton>
          </>
        }
      />
      <FilterRow>
        <Input
          aria-label="Search rules"
          placeholder="Search id or title…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-sm"
          data-testid="rules-search"
        />
        <select
          aria-label="Filter by engine"
          value={engineFilter}
          onChange={(e) => setEngineFilter(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-bny-mist bg-white text-sm"
          data-testid="rules-engine-filter"
        >
          <option value="">All engines</option>
          <option value="freshness">freshness</option>
          <option value="approval">approval</option>
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-bny-mist bg-white text-sm"
          data-testid="rules-status-filter"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="pending_review">Pending review</option>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
        </select>
        <span className="ml-auto text-xs text-bny-fog" data-testid="rules-count">
          {filtered.length} of {items.length}
        </span>
      </FilterRow>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="rules-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Rule ID</Th>
              <Th>Engine</Th>
              <Th>Title</Th>
              <Th className="text-right">Priority</Th>
              <Th>Status</Th>
              <Th>Queue</Th>
              <Th>Tags</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr
                key={r.ruleId}
                className="border-t border-bny-mist hover:bg-bny-paper/60"
                data-testid={`rule-row-${r.ruleId}`}
              >
                <Td>
                  <Link
                    to="/rules/$ruleId"
                    params={{ ruleId: r.ruleId }}
                    className="text-bny-teal hover:underline font-mono text-xs"
                  >
                    {r.ruleId}
                  </Link>
                </Td>
                <Td>
                  <TagPill tone={r.engine === "freshness" ? "knowledge" : "audit"}>
                    {r.engine}
                  </TagPill>
                </Td>
                <Td className="max-w-[300px] truncate">
                  <span className="font-medium">{r.title}</span>
                </Td>
                <Td className="text-right">{r.priority}</Td>
                <Td>
                  <StatusBadge status={r.status} testId={`row-status-${r.ruleId}`} />
                </Td>
                <Td className="text-xs">{r.reviewQueue}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {r.tags.map((t) => (
                      <TagPill key={t} tone={t === "bootstrap" ? "audit" : "neutral"}>
                        {t}
                      </TagPill>
                    ))}
                  </div>
                </Td>
                <Td className="text-right">
                  <button
                    type="button"
                    onClick={() => {
                      const isBootstrap = r.tags.includes("bootstrap");
                      const msg = isBootstrap
                        ? `${r.ruleId} is bootstrap-tagged. Force-delete anyway?`
                        : `Delete ${r.ruleId}?`;
                      if (window.confirm(msg)) {
                        deleteRule(r.ruleId, { force: isBootstrap })
                          .then(refresh)
                          .catch((e) => alert(e.message));
                      }
                    }}
                    className="text-xs text-bny-danger hover:underline"
                    data-testid={`delete-${r.ruleId}`}
                  >
                    Delete
                  </button>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CreateRuleModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => {
          setModalOpen(false);
          // Refresh + give the test a stable hook to find the newly-created row
          refresh();
        }}
      />
    </div>
  );
}

function CreateRuleModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (detail: { ruleId: string }) => void;
}) {
  const [form, setForm] = useState<RuleEditorValue>(blankRuleEditor());
  const [mode, setMode] = useState<"structured" | "json">("structured");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setForm(blankRuleEditor());
      setMode("structured");
      setError(null);
    }
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const detail = await createRule({
        ruleId: form.ruleId,
        engine: form.engine,
        title: form.title,
        description: form.description,
        priority: form.priority,
        when: form.when,
        then: form.then,
        tags: form.tags,
      });
      onCreated(detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New rule" testId="rule-create-modal">
      <form onSubmit={submit}>
        <div className="flex items-center gap-2 mb-3 text-xs">
          <button
            type="button"
            onClick={() => setMode("structured")}
            className={`px-2 py-1 rounded-md border ${
              mode === "structured"
                ? "bg-bny-tealLight border-bny-teal text-bny-ink"
                : "bg-white border-bny-mist text-bny-slate"
            }`}
            data-testid="mode-structured"
          >
            Structured
          </button>
          <button
            type="button"
            onClick={() => setMode("json")}
            className={`px-2 py-1 rounded-md border ${
              mode === "json"
                ? "bg-bny-tealLight border-bny-teal text-bny-ink"
                : "bg-white border-bny-mist text-bny-slate"
            }`}
            data-testid="mode-json"
          >
            JSON
          </button>
        </div>
        <RuleEditor value={form} onChange={setForm} mode={mode} formIdPrefix="rc" />
        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="rule-create-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="rule-create-submit">
            {submitting ? "Saving…" : "Create draft"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

const Th = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <th className={`text-left font-medium px-3 py-2 ${className}`}>{children}</th>
);
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <td className={`px-3 py-2 align-top ${className}`}>{children}</td>
);
