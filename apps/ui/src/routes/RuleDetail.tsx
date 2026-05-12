import { Link, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  approveRule,
  evaluateRule,
  getRule,
  rejectRule,
  submitRule,
  updateRule,
} from "@/api/rules";
import type { RuleDetail } from "@/types/rule";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  Field,
  FormField,
  Input,
  Modal,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  TagPill,
  TextArea,
  formatDate,
} from "@/components/datasets/Common";
import { StatusBadge } from "@/components/rules/StatusBadge";
import { ApprovalModal } from "@/components/rules/ApprovalModal";
import { RuleEditor } from "@/components/rules/RuleEditor";
import { blankRuleEditor, type RuleEditorValue } from "@/components/rules/ruleEditorValue";

export function RuleDetailRoute() {
  const { ruleId } = useParams({ from: "/rules/$ruleId" });
  const [rule, setRule] = useState<RuleDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [evalResult, setEvalResult] = useState<{ fired: boolean; verdict: Record<string, unknown> | null } | null>(null);
  const [evalErr, setEvalErr] = useState<string | null>(null);

  const refresh = () => getRule(ruleId).then(setRule).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ruleId]);

  if (err) return <ErrorBox title="Failed to load rule" detail={err} />;
  if (!rule) return <Loading />;

  const isDraft = rule.status === "draft";
  const isPending = rule.status === "pending_review";
  const editable = isDraft || isPending;

  return (
    <div data-testid="rule-detail-root">
      <PageHeader
        eyebrow="Rule engine · detail"
        title={rule.title}
        subtitle={rule.description}
        actions={
          <>
            <Link to="/rules" className="text-sm text-bny-teal hover:underline">
              ← Rules
            </Link>
            <StatusBadge status={rule.status} testId="rule-status-badge" />
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 mb-4 bg-white border border-bny-mist rounded-lg p-4">
        <Field label="Rule ID" value={<span className="font-mono text-xs" data-testid="detail-rule-id">{rule.ruleId}</span>} />
        <Field label="Engine" value={<TagPill tone={rule.engine === "freshness" ? "knowledge" : "audit"}>{rule.engine}</TagPill>} />
        <Field label="Priority" value={<span data-testid="detail-priority">{rule.priority}</span>} />
        <Field label="Version" value={<span data-testid="detail-version">{rule.version}</span>} />
        <Field label="Review queue" value={rule.reviewQueue} />
        <Field label="Tags" value={
          <div className="flex flex-wrap gap-1">
            {rule.tags.map((t) => (
              <TagPill key={t} tone={t === "bootstrap" ? "audit" : "neutral"}>{t}</TagPill>
            ))}
          </div>
        } />
        <Field label="Created" value={formatDate(rule.createdAt)} />
        <Field label="Updated" value={formatDate(rule.updatedAt)} />
        {rule.submittedBy && <Field label="Submitted by" value={rule.submittedBy} />}
        {rule.approvedAt && <Field label="Approved at" value={<span data-testid="detail-approved-at">{formatDate(rule.approvedAt)}</span>} />}
        {rule.approvedBy && <Field label="Approved by" value={<span data-testid="detail-approved-by">{rule.approvedBy}</span>} />}
        {rule.rationale && <Field label="Rationale" value={rule.rationale} />}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <section className="bg-white border border-bny-mist rounded-lg p-4">
          <h3 className="text-xs uppercase tracking-wider text-bny-fog mb-2">When (condition)</h3>
          <pre className="text-xs font-mono whitespace-pre-wrap" data-testid="detail-when">
{JSON.stringify(rule.when, null, 2)}
          </pre>
        </section>
        <section className="bg-white border border-bny-mist rounded-lg p-4">
          <h3 className="text-xs uppercase tracking-wider text-bny-fog mb-2">Then (verdict)</h3>
          <pre className="text-xs font-mono whitespace-pre-wrap" data-testid="detail-then">
{JSON.stringify(rule.then, null, 2)}
          </pre>
        </section>
      </div>

      <div className="flex items-center gap-2 mb-4">
        {editable && (
          <PrimaryButton onClick={() => setEditOpen(true)} testId="edit-rule-btn">
            Edit
          </PrimaryButton>
        )}
        {isDraft && (
          <PrimaryButton onClick={() => setSubmitOpen(true)} testId="submit-rule-btn">
            Submit for review
          </PrimaryButton>
        )}
        {isPending && (
          <>
            <PrimaryButton onClick={() => setApproveOpen(true)} testId="approve-rule-btn">
              Approve
            </PrimaryButton>
            <SecondaryButton onClick={() => setRejectOpen(true)} tone="danger" testId="reject-rule-btn">
              Reject
            </SecondaryButton>
          </>
        )}
      </div>

      <section className="bg-bny-paper border border-bny-mist rounded-lg p-4">
        <h3 className="text-xs uppercase tracking-wider text-bny-fog mb-2">Live evaluation</h3>
        <p className="text-xs text-bny-slate mb-2">
          Test the rule against a sample input — proves the engine actually drives the agent.
        </p>
        <EvaluationPanel
          ruleId={rule.ruleId}
          engine={rule.engine}
          onResult={(r) => setEvalResult(r)}
          onError={setEvalErr}
        />
        {evalResult && (
          <div
            className="mt-3 p-3 rounded-md bg-white border border-bny-mist text-xs"
            data-testid="eval-result"
          >
            <div className="font-medium mb-1">
              {evalResult.fired ? "✓ Rule fired" : "✗ Rule did not fire"}
            </div>
            {evalResult.verdict && (
              <pre className="font-mono whitespace-pre-wrap" data-testid="eval-verdict">
{JSON.stringify(evalResult.verdict, null, 2)}
              </pre>
            )}
          </div>
        )}
        {evalErr && <div role="alert" className="text-xs text-bny-danger mt-2">{evalErr}</div>}
      </section>

      {editable && (
        <EditModal
          open={editOpen}
          rule={rule}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            refresh();
          }}
        />
      )}

      <SubmitModal
        open={submitOpen}
        ruleId={rule.ruleId}
        onClose={() => setSubmitOpen(false)}
        onSubmitted={() => {
          setSubmitOpen(false);
          refresh();
        }}
      />

      <ApprovalModal
        open={approveOpen}
        title="Approve rule"
        variant="approve"
        onClose={() => setApproveOpen(false)}
        onSubmit={async ({ approver, rationale }) => {
          await approveRule(rule.ruleId, { approver, rationale });
          setApproveOpen(false);
          refresh();
        }}
      />
      <ApprovalModal
        open={rejectOpen}
        title="Reject rule"
        variant="reject"
        onClose={() => setRejectOpen(false)}
        onSubmit={async ({ approver, rationale }) => {
          await rejectRule(rule.ruleId, { approver, rationale });
          setRejectOpen(false);
          refresh();
        }}
      />
    </div>
  );
}

function EditModal({
  open,
  rule,
  onClose,
  onSaved,
}: {
  open: boolean;
  rule: RuleDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<RuleEditorValue>({
    ...blankRuleEditor(rule.engine),
    ruleId: rule.ruleId,
    engine: rule.engine,
    title: rule.title,
    description: rule.description,
    priority: rule.priority,
    tags: rule.tags,
    when: rule.when as never,
    then: rule.then,
    whenJson: JSON.stringify(rule.when, null, 2),
    thenJson: JSON.stringify(rule.then, null, 2),
  });
  const [mode, setMode] = useState<"structured" | "json">("structured");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) setErr(null);
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await updateRule(rule.ruleId, {
        title: form.title,
        description: form.description,
        priority: form.priority,
        when: form.when,
        then: form.then,
        tags: form.tags,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Edit ${rule.ruleId}`} testId="rule-edit-modal">
      <form onSubmit={submit}>
        <div className="flex items-center gap-2 mb-3 text-xs">
          <button type="button" onClick={() => setMode("structured")}
            className={`px-2 py-1 rounded-md border ${mode === "structured" ? "bg-bny-tealLight border-bny-teal" : "bg-white border-bny-mist"}`}
            data-testid="edit-mode-structured">Structured</button>
          <button type="button" onClick={() => setMode("json")}
            className={`px-2 py-1 rounded-md border ${mode === "json" ? "bg-bny-tealLight border-bny-teal" : "bg-white border-bny-mist"}`}
            data-testid="edit-mode-json">JSON</button>
        </div>
        <RuleEditor value={form} onChange={setForm} mode={mode} disableId formIdPrefix="re" />
        {err && <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="rule-edit-error">{err}</div>}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="rule-edit-submit">
            {submitting ? "Saving…" : "Save edit"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

function SubmitModal({
  open,
  ruleId,
  onClose,
  onSubmitted,
}: {
  open: boolean;
  ruleId: string;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await submitRule(ruleId, { submittedBy: name });
      onSubmitted();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Submit for review" testId="submit-modal">
      <form onSubmit={submit}>
        <FormField label="Your name" hint="Will appear in the SME queue">
          <Input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="submit-name"
          />
        </FormField>
        {err && <div role="alert" className="text-xs text-bny-danger mt-2">{err}</div>}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="submit-confirm">
            {submitting ? "Submitting…" : "Submit"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}

function EvaluationPanel({
  ruleId,
  engine,
  onResult,
  onError,
}: {
  ruleId: string;
  engine: "freshness" | "approval";
  onResult: (r: { fired: boolean; verdict: Record<string, unknown> | null }) => void;
  onError: (e: string | null) => void;
}) {
  // Provide a sensible default sample input per engine so the SME can
  // try the rule without crafting JSON by hand.
  const defaultJson = engine === "freshness"
    ? JSON.stringify({
        library_entry: { id: "lib_demo", tags: ["bootstrap", "ops"] },
        evidence: [],
      }, null, 2)
    : JSON.stringify({
        canonical_id: "canon.is.iam",
        classify_confidence: 0.95,
        validate_verdict: "pass",
        pii_halt: true,
        freshness_stale: false,
        consistency_drift: false,
      }, null, 2);

  const [text, setText] = useState(defaultJson);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    onError(null);
    try {
      const ctx = JSON.parse(text);
      const r = await evaluateRule(ruleId, ctx);
      onResult({ fired: r.fired, verdict: r.verdict });
    } catch (e) {
      onError(e instanceof Error ? e.message : "Evaluate failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <TextArea
        rows={6}
        className="font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        data-testid="eval-input"
      />
      <div className="flex items-center justify-end mt-2">
        <PrimaryButton onClick={run} disabled={running} testId="eval-run">
          {running ? "Evaluating…" : "Run evaluation"}
        </PrimaryButton>
      </div>
    </div>
  );
}
