import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  deleteKnowledge,
  getKnowledge,
  updateKnowledge,
} from "@/api/datasets";
import type { KnowledgeDoc, KnowledgeUpdateBody } from "@/types/dataset";
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
} from "@/components/datasets/Common";
import { formatBytes, formatDate } from "@/components/datasets/format";

export function KnowledgeDetailRoute() {
  const { docId } = useParams({ from: "/datasets/knowledge/$docId" });
  const navigate = useNavigate();
  const [doc, setDoc] = useState<KnowledgeDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const refresh = () => getKnowledge(docId).then(setDoc).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  if (err) return <ErrorBox title="Failed to load document" detail={err} />;
  if (!doc) return <Loading />;

  return (
    <div data-testid="knowledge-detail-root">
      <PageHeader
        eyebrow="Knowledge document"
        title={doc.displayTitle}
        subtitle={doc.primaryDesc}
        actions={
          <>
            <button
              type="button"
              onClick={() => navigate({ to: "/datasets/$type", params: { type: "knowledge" } })}
              className="text-sm text-bny-teal hover:underline"
              data-testid="back-to-list"
            >
              ← Knowledge
            </button>
            <SecondaryButton onClick={() => setEditing(true)} testId="edit-knowledge-btn">
              Edit
            </SecondaryButton>
            <SecondaryButton
              tone="danger"
              testId="delete-knowledge-btn"
              onClick={() => {
                if (window.confirm(`Delete ${doc.docId}? Metadata only — S3 object is not affected.`)) {
                  deleteKnowledge(doc.docId).then(() =>
                    navigate({ to: "/datasets/$type", params: { type: "knowledge" } }),
                  );
                }
              }}
            >
              Delete
            </SecondaryButton>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-6 max-w-3xl">
        <Field label="Doc ID" value={<span className="font-mono text-xs">{doc.docId}</span>} />
        <Field label="Source" value={<TagPill tone="knowledge">{doc.source}</TagPill>} />
        <Field label="Entity" value={doc.entity} />
        <Field label="Kind" value={doc.kind || "—"} />
        <Field label="Effective date" value={doc.effectiveDate || "—"} />
        <Field label="Size" value={formatBytes(doc.bytes)} />
        <Field label="Content type" value={<span className="font-mono text-xs">{doc.contentType}</span>} />
        <Field label="Ingested" value={formatDate(doc.ingestedAt)} />
        <Field label="Last updated" value={formatDate(doc.updatedAt)} />
        <Field
          label="Tags"
          value={
            <div className="flex flex-wrap gap-1 mt-0.5">
              {doc.tags.length === 0
                ? "—"
                : doc.tags.map((t) => <TagPill key={t}>{t}</TagPill>)}
            </div>
          }
        />
      </div>
      <div className="mt-6 max-w-3xl">
        <Field label="Doc hash (content address)" value={<code className="text-xs break-all">{doc.docHash}</code>} />
      </div>
      <div className="mt-3 max-w-3xl">
        <Field label="S3 URI" value={<code className="text-xs break-all">{doc.s3Uri}</code>} />
      </div>
      {doc.url && (
        <div className="mt-3 max-w-3xl">
          <Field label="Source URL" value={
            <a href={doc.url} target="_blank" rel="noreferrer" className="text-bny-teal hover:underline text-xs break-all">
              {doc.url}
            </a>
          } />
        </div>
      )}

      <KnowledgeEditModal
        open={editing}
        doc={doc}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          refresh();
        }}
      />
    </div>
  );
}

function KnowledgeEditModal({
  open,
  doc,
  onClose,
  onSaved,
}: {
  open: boolean;
  doc: KnowledgeDoc;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<KnowledgeUpdateBody>({
    primaryDesc: doc.primaryDesc,
    kind: doc.kind,
    effectiveDate: doc.effectiveDate,
    tags: doc.tags,
    url: doc.url,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm({
      primaryDesc: doc.primaryDesc,
      kind: doc.kind,
      effectiveDate: doc.effectiveDate,
      tags: doc.tags,
      url: doc.url,
    });
  }, [doc]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await updateKnowledge(doc.docId, form);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Edit ${doc.docId}`} testId="knowledge-edit-modal">
      <form onSubmit={submit}>
        <FormField label="Primary description">
          <Input
            value={form.primaryDesc ?? ""}
            onChange={(e) => setForm({ ...form, primaryDesc: e.target.value })}
            data-testid="kn-edit-desc"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Kind">
            <Input
              value={form.kind ?? ""}
              onChange={(e) => setForm({ ...form, kind: e.target.value || null })}
            />
          </FormField>
          <FormField label="Effective date">
            <Input
              type="date"
              value={form.effectiveDate ?? ""}
              onChange={(e) =>
                setForm({ ...form, effectiveDate: e.target.value || null })
              }
            />
          </FormField>
        </div>
        <FormField label="Tags" hint="Comma-separated">
          <Input
            value={(form.tags ?? []).join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                tags: e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
            data-testid="kn-edit-tags"
          />
        </FormField>
        <FormField label="Source URL">
          <Input
            value={form.url ?? ""}
            onChange={(e) => setForm({ ...form, url: e.target.value || null })}
          />
        </FormField>
        <div className="text-[11px] text-bny-fog">
          Doc hash, S3 URI, source, entity, and bytes are immutable — content-addressed.
        </div>
        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="kn-edit-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="kn-edit-submit">
            {submitting ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}
