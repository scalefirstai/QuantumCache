import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  deleteCanonical,
  getCanonical,
  updateCanonical,
} from "@/api/datasets";
import type {
  CanonicalDetail,
  CanonicalUpdateBody,
  FrameworkMapping,
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
  TagPill,
  TextArea,
  formatDate,
} from "@/components/datasets/Common";

export function CanonicalDetailRoute() {
  const { canonicalId } = useParams({ from: "/datasets/canonical/$canonicalId" });
  const navigate = useNavigate();
  const [item, setItem] = useState<CanonicalDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const refresh = () =>
    getCanonical(canonicalId).then(setItem).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
  }, [canonicalId]);

  if (err) return <ErrorBox title="Failed to load canonical" detail={err} />;
  if (!item) return <Loading />;

  const isBootstrap = item.tags.includes("bootstrap");

  return (
    <div data-testid="canonical-detail-root">
      <PageHeader
        eyebrow="Canonical question"
        title={item.label}
        subtitle={item.description}
        actions={
          <>
            <button
              type="button"
              onClick={() => navigate({ to: "/datasets/$type", params: { type: "canonical" } })}
              className="text-sm text-bny-teal hover:underline"
            >
              ← Canonical
            </button>
            <SecondaryButton onClick={() => setEditing(true)} testId="edit-canonical-btn">
              Edit
            </SecondaryButton>
            <SecondaryButton
              tone="danger"
              testId="delete-canonical-btn"
              onClick={() => {
                const msg = isBootstrap
                  ? `${item.canonicalId} is bootstrap-tagged. Force-delete anyway?`
                  : `Delete ${item.canonicalId}?`;
                if (window.confirm(msg)) {
                  deleteCanonical(item.canonicalId, { force: isBootstrap })
                    .then(() =>
                      navigate({ to: "/datasets/$type", params: { type: "canonical" } }),
                    )
                    .catch((e) => alert(e.message));
                }
              }}
            >
              Delete
            </SecondaryButton>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-6 max-w-3xl">
        <Field label="Canonical ID" value={<span className="font-mono text-xs">{item.canonicalId}</span>} />
        <Field
          label="Tier"
          value={
            <TagPill tone={item.tier === 1 ? "danger" : item.tier === 3 ? "neutral" : "canonical"}>
              Tier {item.tier}
            </TagPill>
          }
        />
        <Field label="Parent" value={item.parentId ? <span className="font-mono text-xs">{item.parentId}</span> : "—"} />
        <Field label="Do not answer" value={item.doNotAnswer ? <TagPill tone="danger">yes</TagPill> : "no"} />
        <Field label="Owners" value={item.owners.join(", ") || "—"} />
        <Field
          label="Tags"
          value={
            <div className="flex flex-wrap gap-1 mt-0.5">
              {item.tags.map((t) => (
                <TagPill key={t} tone={t === "bootstrap" ? "audit" : "neutral"}>
                  {t}
                </TagPill>
              ))}
            </div>
          }
        />
        <Field label="Created" value={formatDate(item.createdAt)} />
        <Field label="Updated" value={formatDate(item.updatedAt)} />
      </div>
      <section className="mt-6 max-w-3xl">
        <div className="text-[10px] uppercase tracking-wider text-bny-fog mb-1">
          Framework mappings
        </div>
        <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm" data-testid="framework-mappings-table">
            <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
              <tr>
                <th className="text-left font-medium px-3 py-2">Framework</th>
                <th className="text-left font-medium px-3 py-2">Version</th>
                <th className="text-left font-medium px-3 py-2">Question Ref</th>
              </tr>
            </thead>
            <tbody>
              {item.frameworkMappings.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-xs text-bny-fog">
                    No framework mappings — this canonical is internal-only.
                  </td>
                </tr>
              ) : (
                item.frameworkMappings.map((m, i) => (
                  <tr key={i} className="border-t border-bny-mist">
                    <td className="px-3 py-2 font-mono text-xs">{m.framework}</td>
                    <td className="px-3 py-2 font-mono text-xs">{m.version}</td>
                    <td className="px-3 py-2 font-mono text-xs">{m.questionRef}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <CanonicalEditModal
        open={editing}
        item={item}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false);
          refresh();
        }}
      />
    </div>
  );
}

function CanonicalEditModal({
  open,
  item,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: CanonicalDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<CanonicalUpdateBody>({
    label: item.label,
    description: item.description,
    tier: item.tier,
    doNotAnswer: item.doNotAnswer,
    owners: item.owners,
    tags: item.tags,
    frameworkMappings: item.frameworkMappings,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm({
      label: item.label,
      description: item.description,
      tier: item.tier,
      doNotAnswer: item.doNotAnswer,
      owners: item.owners,
      tags: item.tags,
      frameworkMappings: item.frameworkMappings,
    });
  }, [item]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await updateCanonical(item.canonicalId, form);
      onSaved();
    } catch (e: any) {
      setError(e?.message ?? "Update failed");
    } finally {
      setSubmitting(false);
    }
  };

  const setMapping = (i: number, patch: Partial<FrameworkMapping>) => {
    const next = (form.frameworkMappings ?? []).map((m, idx) =>
      idx === i ? { ...m, ...patch } : m,
    );
    setForm({ ...form, frameworkMappings: next });
  };

  return (
    <Modal open={open} onClose={onClose} title={`Edit ${item.canonicalId}`} testId="canonical-edit-modal">
      <form onSubmit={submit}>
        <FormField label="Label">
          <Input
            value={form.label ?? ""}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            data-testid="cn-edit-label"
          />
        </FormField>
        <FormField label="Description">
          <TextArea
            rows={3}
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Tier">
            <Select
              value={form.tier}
              onChange={(e) =>
                setForm({ ...form, tier: Number(e.target.value) as 1 | 2 | 3 })
              }
            >
              <option value={1}>Tier 1</option>
              <option value={2}>Tier 2</option>
              <option value={3}>Tier 3</option>
            </Select>
          </FormField>
          <FormField label="Do not answer">
            <label className="flex items-center gap-2 text-xs mt-2">
              <input
                type="checkbox"
                checked={form.doNotAnswer ?? false}
                onChange={(e) => setForm({ ...form, doNotAnswer: e.target.checked })}
              />
              Refuse via guardrail
            </label>
          </FormField>
        </div>
        <FormField label="Tags" hint="Comma-separated">
          <Input
            value={(form.tags ?? []).join(", ")}
            onChange={(e) =>
              setForm({
                ...form,
                tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
            data-testid="cn-edit-tags"
          />
        </FormField>
        <div className="mb-2 text-sm font-medium">Framework mappings</div>
        <div className="space-y-2">
          {(form.frameworkMappings ?? []).map((m, i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-center">
              <Input
                value={m.framework}
                onChange={(e) => setMapping(i, { framework: e.target.value })}
                placeholder="framework"
              />
              <Input
                value={m.version}
                onChange={(e) => setMapping(i, { version: e.target.value })}
                placeholder="version"
              />
              <Input
                value={m.questionRef}
                onChange={(e) => setMapping(i, { questionRef: e.target.value })}
                placeholder="question_ref"
              />
              <button
                type="button"
                aria-label={`Remove mapping ${i + 1}`}
                onClick={() =>
                  setForm({
                    ...form,
                    frameworkMappings: (form.frameworkMappings ?? []).filter(
                      (_, idx) => idx !== i,
                    ),
                  })
                }
                className="text-xs text-bny-danger px-2 py-1.5 rounded-md hover:bg-bny-danger/10"
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setForm({
                ...form,
                frameworkMappings: [
                  ...(form.frameworkMappings ?? []),
                  { framework: "", version: "", questionRef: "" },
                ],
              })
            }
            className="text-xs text-bny-teal hover:underline"
            data-testid="cn-edit-add-mapping"
          >
            + add mapping
          </button>
        </div>
        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="cn-edit-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="cn-edit-submit">
            {submitting ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      </form>
    </Modal>
  );
}
