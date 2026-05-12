import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  createAuditRedaction,
  getAudit,
  listAuditRedactions,
  verifyAudit,
} from "@/api/datasets";
import type {
  AuditRedaction,
  AuditRunDetail,
  AuditVerifyResult,
} from "@/types/dataset";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  Field,
  FormField,
  Input,
  Modal,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Select,
  TextArea,
  VerdictPill,
  formatDate,
} from "@/components/datasets/Common";

export function AuditDetailRoute() {
  const { runId } = useParams({ from: "/datasets/audit/$runId" });
  const navigate = useNavigate();
  const [run, setRun] = useState<AuditRunDetail | null>(null);
  const [redactions, setRedactions] = useState<AuditRedaction[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verify, setVerify] = useState<AuditVerifyResult | null>(null);
  const [redactOpen, setRedactOpen] = useState(false);

  const refresh = () => {
    getAudit(runId).then(setRun).catch((e) => setErr(String(e)));
    listAuditRedactions(runId)
      .then(setRedactions)
      .catch(() => setRedactions([]));
  };

  useEffect(() => {
    refresh();
  }, [runId]);

  if (err) return <ErrorBox title="Failed to load audit run" detail={err} />;
  if (!run) return <Loading />;

  const runVerify = async () => {
    setVerifying(true);
    try {
      setVerify(await verifyAudit(runId));
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div data-testid="audit-detail-root">
      <PageHeader
        eyebrow="Audit run · immutable"
        title={run.runId}
        subtitle={run.input?.text ?? "Sealed L01 journal"}
        actions={
          <>
            <button
              type="button"
              onClick={() => navigate({ to: "/datasets/$type", params: { type: "audit" } })}
              className="text-sm text-bny-teal hover:underline"
            >
              ← Audit
            </button>
            <SecondaryButton onClick={runVerify} testId="verify-btn">
              {verifying ? "Verifying…" : "Verify integrity"}
            </SecondaryButton>
            <SecondaryButton onClick={() => setRedactOpen(true)} testId="redact-btn">
              + Redact
            </SecondaryButton>
          </>
        }
      />

      {verify && (
        <div
          data-testid="verify-result"
          className={`mb-5 border rounded-lg p-3 text-sm max-w-3xl ${
            verify.chainOk && verify.merkleOk
              ? "border-bny-ok/40 bg-bny-ok/5"
              : "border-bny-danger/40 bg-bny-danger/5"
          }`}
        >
          <div className="font-medium mb-1">
            {verify.chainOk && verify.merkleOk
              ? "✓ Integrity verified"
              : "✗ Integrity check failed"}
          </div>
          <div className="text-xs text-bny-slate">
            chain: {verify.chainOk ? "ok" : `broken at ${verify.brokenAt}`} · merkle:{" "}
            {verify.merkleOk ? "ok" : "mismatch"} · checked at{" "}
            {formatDate(verify.verifiedAt)}
          </div>
          <div className="text-[10px] text-bny-fog mt-1 break-all font-mono">
            recomputed: {verify.recomputedMerkle}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6 max-w-3xl">
        <Field label="DDQ ID" value={run.ddqId ? <span className="font-mono text-xs">{run.ddqId}</span> : "—"} />
        <Field label="Verdict" value={<VerdictPill verdict={run.verdict ?? ""} />} />
        <Field label="Framework" value={run.input?.framework ?? "—"} />
        <Field label="Route" value={run.route ?? "—"} />
        <Field label="Platform" value={run.platformVersion ?? "—"} />
        <Field label="Sealed" value={formatDate(run.sealedAt)} />
        <Field
          label="Taxonomy"
          value={<span className="font-mono text-xs">{run.taxonomyVersion ?? "—"}</span>}
        />
        <Field
          label="Library"
          value={<span className="font-mono text-xs">{run.libraryVersion ?? "—"}</span>}
        />
      </div>

      <div className="mt-4 max-w-3xl">
        <Field
          label="Merkle root"
          value={<code className="text-xs break-all">{run.merkleRoot}</code>}
        />
      </div>

      <section className="mt-6 max-w-3xl">
        <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
          Event chain · {run.events.length} events
        </div>
        <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm" data-testid="audit-events-table">
            <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
              <tr>
                <th className="text-left font-medium px-3 py-2">#</th>
                <th className="text-left font-medium px-3 py-2">Kind</th>
                <th className="text-left font-medium px-3 py-2">Agent</th>
                <th className="text-left font-medium px-3 py-2">Time</th>
                <th className="text-left font-medium px-3 py-2">Chain hash</th>
              </tr>
            </thead>
            <tbody>
              {run.events.map((e, i) => (
                <tr key={e.eventId} className="border-t border-bny-mist">
                  <td className="px-3 py-2 font-mono text-xs text-bny-fog">{i + 1}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.kind}</td>
                  <td className="px-3 py-2 text-xs">{e.agent || "—"}</td>
                  <td className="px-3 py-2 text-xs text-bny-fog">{formatDate(e.ts)}</td>
                  <td className="px-3 py-2 font-mono text-[10px] text-bny-slate break-all">
                    {e.chainHash?.slice(0, 32)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-6 max-w-3xl">
        <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
          Redactions · {redactions.length}
        </div>
        {redactions.length === 0 ? (
          <p className="text-sm text-bny-fog border border-dashed border-bny-mist rounded-lg p-4">
            No redactions on this run. Redactions are append-only (sealed records are
            never rewritten).
          </p>
        ) : (
          <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
            <table className="w-full text-sm" data-testid="redactions-table">
              <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
                <tr>
                  <th className="text-left font-medium px-3 py-2">Event</th>
                  <th className="text-left font-medium px-3 py-2">Field</th>
                  <th className="text-left font-medium px-3 py-2">Reason</th>
                  <th className="text-left font-medium px-3 py-2">Actor</th>
                  <th className="text-left font-medium px-3 py-2">When</th>
                </tr>
              </thead>
              <tbody>
                {redactions.map((r) => (
                  <tr key={r.redactionId} className="border-t border-bny-mist">
                    <td className="px-3 py-2 font-mono text-xs">{r.eventId.slice(0, 16)}…</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.field}</td>
                    <td className="px-3 py-2 text-xs">{r.reason}</td>
                    <td className="px-3 py-2 text-xs">{r.actor}</td>
                    <td className="px-3 py-2 text-xs text-bny-fog">{formatDate(r.ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <RedactionModal
        open={redactOpen}
        run={run}
        onClose={() => setRedactOpen(false)}
        onCreated={() => {
          setRedactOpen(false);
          refresh();
        }}
      />
    </div>
  );
}

function RedactionModal({
  open,
  run,
  onClose,
  onCreated,
}: {
  open: boolean;
  run: AuditRunDetail;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState({
    eventId: run.events[0]?.eventId ?? "",
    field: "payload.evidence_excerpt",
    reason: "",
    actor: "operator",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm((f) => ({ ...f, eventId: run.events[0]?.eventId ?? "" }));
  }, [run.runId, run.events.length]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createAuditRedaction(run.runId, form);
      onCreated();
    } catch (e: any) {
      setError(e?.message ?? "Redaction failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Append redaction record" testId="redaction-modal">
      <p className="text-xs text-bny-slate mb-3">
        The sealed run JSON is never rewritten. The redaction is logged in a side
        record so downstream consumers can mask the field at read time.
      </p>
      <form onSubmit={submit}>
        <FormField label="Event">
          <Select
            value={form.eventId}
            onChange={(e) => setForm({ ...form, eventId: e.target.value })}
            data-testid="redact-event"
          >
            {run.events.map((e) => (
              <option key={e.eventId} value={e.eventId}>
                {e.kind} · {e.eventId.slice(0, 16)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Field path" hint="e.g., payload.evidence_excerpt">
          <Input
            required
            value={form.field}
            onChange={(e) => setForm({ ...form, field: e.target.value })}
            data-testid="redact-field"
          />
        </FormField>
        <FormField label="Reason" hint="Legal hold or ticket reference">
          <TextArea
            required
            rows={3}
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
            data-testid="redact-reason"
          />
        </FormField>
        <FormField label="Actor">
          <Input
            required
            value={form.actor}
            onChange={(e) => setForm({ ...form, actor: e.target.value })}
          />
        </FormField>
        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="redact-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="redact-submit">
            {submitting ? "Saving…" : "Append"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}
