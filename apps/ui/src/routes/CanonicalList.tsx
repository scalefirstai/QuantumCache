import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  createCanonical,
  deleteCanonical,
  listCanonical,
} from "@/api/datasets";
import type {
  CanonicalCreateBody,
  CanonicalDetail,
} from "@/types/dataset";
import { Loading, ErrorBox } from "@/components/shell/StateMessages";
import {
  FilterRow,
  FormField,
  Input,
  Modal,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  Select,
  TagPill,
  TextArea,
} from "@/components/datasets/Common";
import { Pagination } from "@/components/datasets/Pagination";
import {
  DEFAULT_PAGE_SIZE,
  paginate,
  type PageSize,
} from "@/components/datasets/paginationUtils";

export function CanonicalListRoute() {
  const [items, setItems] = useState<CanonicalDetail[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("");
  const [modalOpen, setModalOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setPage(0);
  }, [query, tierFilter]);

  const refresh = () => listCanonical().then(setItems).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
  }, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.toLowerCase();
    return items.filter((c) => {
      if (tierFilter && String(c.tier) !== tierFilter) return false;
      if (!q) return true;
      return (
        c.canonicalId.toLowerCase().includes(q) ||
        c.label.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.frameworkMappings.some((m) =>
          m.questionRef.toLowerCase().includes(q) ||
          m.framework.toLowerCase().includes(q),
        )
      );
    });
  }, [items, query, tierFilter]);

  const { pageItems, total } = useMemo(
    () => paginate(filtered, page, pageSize),
    [filtered, page, pageSize],
  );

  if (err) return <ErrorBox title="Failed to load canonical" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="canonical-list-root">
      <PageHeader
        eyebrow="Datasets · Canonical"
        title="Canonical taxonomy"
        subtitle="The single source of truth for how DDQ questions across frameworks resolve to a canonical answer slot."
        actions={
          <>
            <Link to="/datasets" className="text-sm text-bny-teal hover:underline">
              ← Datasets
            </Link>
            <PrimaryButton onClick={() => setModalOpen(true)} testId="add-canonical-btn">
              + Add canonical
            </PrimaryButton>
          </>
        }
      />
      <FilterRow>
        <Input
          aria-label="Search canonical"
          placeholder="Search id, label, question_ref…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-sm"
          data-testid="canonical-search"
        />
        <select
          aria-label="Filter by tier"
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          className="px-2 py-1.5 rounded-md border border-bny-mist bg-white text-sm"
          data-testid="canonical-tier-filter"
        >
          <option value="">All tiers</option>
          <option value="1">Tier 1 — high risk</option>
          <option value="2">Tier 2 — standard</option>
          <option value="3">Tier 3 — low</option>
        </select>
        <span className="ml-auto text-xs text-bny-fog" data-testid="canonical-count">
          {filtered.length} of {items.length}
        </span>
      </FilterRow>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="canonical-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Canonical ID</Th>
              <Th>Label</Th>
              <Th className="text-right">Tier</Th>
              <Th>Owners</Th>
              <Th>Mappings</Th>
              <Th>Tags</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((c) => (
              <tr
                key={c.canonicalId}
                className="border-t border-bny-mist hover:bg-bny-paper/60"
                data-testid={`canonical-row-${c.canonicalId}`}
              >
                <Td>
                  <Link
                    to="/datasets/canonical/$canonicalId"
                    params={{ canonicalId: c.canonicalId }}
                    className="text-bny-teal hover:underline font-mono text-xs"
                  >
                    {c.canonicalId}
                  </Link>
                </Td>
                <Td className="max-w-[280px]">
                  <div className="font-medium">{c.label}</div>
                  <div className="text-[11px] text-bny-fog mt-0.5 line-clamp-2">
                    {c.description}
                  </div>
                </Td>
                <Td className="text-right">
                  <TagPill tone={c.tier === 1 ? "danger" : c.tier === 3 ? "neutral" : "canonical"}>
                    T{c.tier}
                  </TagPill>
                </Td>
                <Td className="text-xs">
                  {c.owners.join(", ") || "—"}
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {c.frameworkMappings.slice(0, 3).map((m, i) => (
                      <TagPill key={i}>
                        {m.framework}:{m.questionRef}
                      </TagPill>
                    ))}
                    {c.frameworkMappings.length > 3 && (
                      <TagPill>+{c.frameworkMappings.length - 3}</TagPill>
                    )}
                  </div>
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {c.tags.map((t) => (
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
                      const isBootstrap = c.tags.includes("bootstrap");
                      const msg = isBootstrap
                        ? `${c.canonicalId} is bootstrap-tagged. Force-delete anyway?`
                        : `Delete ${c.canonicalId}?`;
                      if (window.confirm(msg)) {
                        deleteCanonical(c.canonicalId, { force: isBootstrap })
                          .then(refresh)
                          .catch((e) => alert(e.message));
                      }
                    }}
                    className="text-xs text-bny-danger hover:underline"
                    data-testid={`delete-${c.canonicalId}`}
                  >
                    Delete
                  </button>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={(s) => {
          setPageSize(s);
          setPage(0);
        }}
        testId="canonical-pagination"
      />
      <CanonicalCreateModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={() => {
          setModalOpen(false);
          refresh();
        }}
      />
    </div>
  );
}

function CanonicalCreateModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CanonicalCreateBody>({
    canonicalId: "",
    label: "",
    description: "",
    tier: 2,
    doNotAnswer: false,
    owners: ["operator"],
    tags: ["operator-added"],
    frameworkMappings: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createCanonical(form);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add canonical question" testId="canonical-create-modal">
      <form onSubmit={submit}>
        <FormField label="Canonical ID" hint="dot-separated, e.g., canon.is.iam.mfa_app_q1">
          <Input
            required
            pattern="[A-Za-z0-9._\-]+"
            value={form.canonicalId}
            onChange={(e) => setForm({ ...form, canonicalId: e.target.value })}
            data-testid="cn-create-id"
          />
        </FormField>
        <FormField label="Label">
          <Input
            required
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            data-testid="cn-create-label"
          />
        </FormField>
        <FormField label="Description">
          <TextArea
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            data-testid="cn-create-desc"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Tier" hint="1 high · 2 standard · 3 low">
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
          <FormField label="Owners" hint="Comma-separated">
            <Input
              value={(form.owners ?? []).join(", ")}
              onChange={(e) =>
                setForm({
                  ...form,
                  owners: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                })
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
                tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
          />
        </FormField>
        <FormField label="Do not answer">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={form.doNotAnswer ?? false}
              onChange={(e) => setForm({ ...form, doNotAnswer: e.target.checked })}
              data-testid="cn-create-dna"
            />
            Refuse via guardrail (e.g., adversarial-recon)
          </label>
        </FormField>
        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-2" data-testid="cn-create-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton type="submit" disabled={submitting} testId="cn-create-submit">
            {submitting ? "Saving…" : "Create"}
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
