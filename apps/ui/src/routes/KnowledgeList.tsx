import { Link } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  confirmKnowledgeUpload,
  deleteKnowledge,
  listKnowledge,
  putKnowledgeUploadObject,
  requestKnowledgeUpload,
} from "@/api/datasets";
import type {
  KnowledgeDoc,
  KnowledgeUploadTicket,
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
  TagPill,
} from "@/components/datasets/Common";
import { formatBytes } from "@/components/datasets/format";
import { Pagination } from "@/components/datasets/Pagination";
import {
  DEFAULT_PAGE_SIZE,
  paginate,
  type PageSize,
} from "@/components/datasets/paginationUtils";

export function KnowledgeListRoute() {
  const [items, setItems] = useState<KnowledgeDoc[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [modalOpen, setModalOpen] = useState(false);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<PageSize>(DEFAULT_PAGE_SIZE);

  // Filter changes always reset to page 0 — staying on page 7 when a
  // filter would only return 3 rows is bad UX.
  useEffect(() => {
    setPage(0);
  }, [query, sourceFilter]);

  const refresh = () =>
    listKnowledge().then(setItems).catch((e) => setErr(String(e)));

  useEffect(() => {
    refresh();
  }, []);

  const sources = useMemo(() => {
    if (!items) return [];
    return Array.from(new Set(items.map((d) => d.source))).sort();
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.toLowerCase();
    return items.filter((d) => {
      if (sourceFilter && d.source !== sourceFilter) return false;
      if (!q) return true;
      return (
        d.docId.toLowerCase().includes(q) ||
        d.primaryDesc.toLowerCase().includes(q) ||
        d.entity.toLowerCase().includes(q) ||
        d.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [items, query, sourceFilter]);

  const { pageItems, total } = useMemo(
    () => paginate(filtered, page, pageSize),
    [filtered, page, pageSize],
  );

  if (err) return <ErrorBox title="Failed to load knowledge" detail={err} />;
  if (!items) return <Loading />;

  return (
    <div data-testid="knowledge-list-root">
      <PageHeader
        eyebrow="Datasets · Knowledge"
        title="Knowledge corpus"
        subtitle="Source documents the retrieval layer queries against. Edits update metadata only; bytes are content-addressed and immutable."
        actions={
          <>
            <Link
              to="/datasets"
              className="text-sm text-bny-teal hover:underline"
              data-testid="back-to-datasets"
            >
              ← Datasets
            </Link>
            <PrimaryButton
              onClick={() => setModalOpen(true)}
              testId="add-knowledge-btn"
            >
              + Add document
            </PrimaryButton>
          </>
        }
      />
      <FilterRow>
        <Input
          aria-label="Search knowledge documents"
          placeholder="Search docId, entity, description, tag…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-sm"
          data-testid="knowledge-search"
        />
        <select
          aria-label="Filter by source"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          data-testid="knowledge-source-filter"
          className="px-2 py-1.5 rounded-md border border-bny-mist bg-white text-sm"
        >
          <option value="">All sources</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-bny-fog" data-testid="knowledge-count">
          {filtered.length} of {items.length}
        </span>
      </FilterRow>
      <div className="border border-bny-mist rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm" data-testid="knowledge-table">
          <thead className="text-xs uppercase tracking-wide bg-bny-paper text-bny-fog">
            <tr>
              <Th>Document</Th>
              <Th>Source</Th>
              <Th>Kind</Th>
              <Th>Effective</Th>
              <Th className="text-right">Size</Th>
              <Th>Tags</Th>
              <Th className="text-right">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((d) => (
              <tr
                key={d.docId}
                className="border-t border-bny-mist hover:bg-bny-paper/60"
                data-testid={`knowledge-row-${d.docId}`}
              >
                <Td>
                  <Link
                    to="/datasets/knowledge/$docId"
                    params={{ docId: d.docId }}
                    className="text-bny-teal hover:underline font-medium"
                  >
                    {d.displayTitle}
                  </Link>
                  <div className="text-[11px] text-bny-fog font-mono mt-0.5">
                    {d.docId}
                  </div>
                </Td>
                <Td>
                  <TagPill tone="knowledge">{d.source}</TagPill>
                </Td>
                <Td className="text-xs">{d.kind || "—"}</Td>
                <Td className="text-xs font-mono">{d.effectiveDate || "—"}</Td>
                <Td className="text-xs text-right font-mono">{formatBytes(d.bytes)}</Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {d.tags.map((t) => (
                      <TagPill key={t}>{t}</TagPill>
                    ))}
                  </div>
                </Td>
                <Td className="text-right">
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`Delete ${d.docId}? Metadata only — S3 object is not affected.`)) {
                        deleteKnowledge(d.docId).then(refresh).catch((e) => alert(e.message));
                      }
                    }}
                    className="text-xs text-bny-danger hover:underline"
                    data-testid={`delete-${d.docId}`}
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
        testId="knowledge-pagination"
      />
      <KnowledgeCreateModal
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

type UploadStage = "idle" | "hashing" | "presigning" | "uploading" | "confirming";

interface UploadMeta {
  docId: string;
  source: string;
  entity: string;
  primaryDesc: string;
  kind: string;
  effectiveDate: string;
  url: string;
  tags: string;
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/\.[a-z0-9]+$/, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

function suggestDocId(filename: string, kind: string): string {
  const k = slugify(kind) || "doc";
  const base = slugify(filename) || "upload";
  return `operator:${k}:${base}`;
}

async function sha256OfFile(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return `sha256:${hex}`;
}

function KnowledgeCreateModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [docHash, setDocHash] = useState<string | null>(null);
  const [stage, setStage] = useState<UploadStage>("idle");
  const [putProgress, setPutProgress] = useState(0); // 0..1
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<UploadMeta>({
    docId: "",
    source: "operator",
    entity: "bny-mellon-corp",
    primaryDesc: "",
    kind: "policy",
    effectiveDate: "",
    url: "",
    tags: "operator-added",
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset whenever the modal toggles.
  useEffect(() => {
    if (!open) {
      setFile(null);
      setDocHash(null);
      setStage("idle");
      setPutProgress(0);
      setError(null);
      setMeta({
        docId: "",
        source: "operator",
        entity: "bny-mellon-corp",
        primaryDesc: "",
        kind: "policy",
        effectiveDate: "",
        url: "",
        tags: "operator-added",
      });
    }
  }, [open]);

  const acceptFile = async (f: File) => {
    setError(null);
    setFile(f);
    setDocHash(null);
    setStage("hashing");
    setMeta((m) => ({
      ...m,
      docId: m.docId || suggestDocId(f.name, m.kind),
      primaryDesc: m.primaryDesc || f.name.replace(/\.[a-z0-9]+$/i, ""),
    }));
    try {
      const hash = await sha256OfFile(f);
      setDocHash(hash);
      setStage("idle");
    } catch (e) {
      setError(`Hashing failed: ${e instanceof Error ? e.message : String(e)}`);
      setStage("idle");
    }
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) acceptFile(f);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !docHash) {
      setError("Drop a file first.");
      return;
    }
    setError(null);
    let ticket: KnowledgeUploadTicket;
    try {
      setStage("presigning");
      ticket = await requestKnowledgeUpload({
        filename: file.name,
        contentType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        source: meta.source,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get upload URL");
      setStage("idle");
      return;
    }

    try {
      setStage("uploading");
      setPutProgress(0);
      await putKnowledgeUploadObject(ticket, file, (loaded, total) => {
        setPutProgress(total > 0 ? loaded / total : 0);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setStage("idle");
      return;
    }

    try {
      setStage("confirming");
      await confirmKnowledgeUpload({
        key: ticket.key,
        docId: meta.docId,
        source: meta.source,
        entity: meta.entity,
        primaryDesc: meta.primaryDesc,
        contentType: file.type || "application/octet-stream",
        kind: meta.kind || null,
        effectiveDate: meta.effectiveDate || null,
        url: meta.url || null,
        tags: meta.tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        clientDocHash: docHash,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed");
      setStage("idle");
    }
  };

  const busy = stage !== "idle";
  const stageLabel: Record<UploadStage, string> = {
    idle: file ? "Save document" : "Drop a file to begin",
    hashing: "Hashing…",
    presigning: "Requesting upload URL…",
    uploading: `Uploading ${(putProgress * 100).toFixed(0)}%…`,
    confirming: "Confirming…",
  };

  return (
    <Modal open={open} onClose={onClose} title="Add knowledge document" testId="knowledge-create-modal">
      <form onSubmit={submit}>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
          }}
          data-testid="kn-dropzone"
          className={`mb-4 cursor-pointer rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${
            dragOver
              ? "border-bny-teal bg-bny-teal/5"
              : file
                ? "border-bny-mist bg-bny-paper/60"
                : "border-bny-mist hover:border-bny-teal hover:bg-bny-paper/40"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            data-testid="kn-file-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) acceptFile(f);
              e.currentTarget.value = "";
            }}
          />
          {file ? (
            <div className="space-y-1 text-left">
              <div className="text-sm font-medium" data-testid="kn-file-name">
                {file.name}
              </div>
              <div className="text-xs text-bny-fog">
                {formatBytes(file.size)} · {file.type || "unknown type"}
              </div>
              {docHash ? (
                <div className="text-[10px] font-mono text-bny-fog break-all" data-testid="kn-file-hash">
                  {docHash}
                </div>
              ) : (
                <div className="text-xs text-bny-teal">Hashing…</div>
              )}
              <button
                type="button"
                className="mt-1 text-xs text-bny-teal hover:underline"
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                  setDocHash(null);
                }}
              >
                Choose a different file
              </button>
            </div>
          ) : (
            <div className="text-sm text-bny-slate">
              <div className="font-medium">Drop a document here</div>
              <div className="text-xs text-bny-fog mt-1">
                or click to browse · PDF / DOCX / HTML / TXT · up to 200 MB
              </div>
            </div>
          )}
        </div>

        <FormField label="Doc ID" hint="Globally unique (e.g., operator:policy:2026-q2-aup)">
          <Input
            required
            value={meta.docId}
            onChange={(e) => setMeta({ ...meta, docId: e.target.value })}
            data-testid="kn-create-docId"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Source">
            <Input
              required
              value={meta.source}
              onChange={(e) => setMeta({ ...meta, source: e.target.value })}
              data-testid="kn-create-source"
            />
          </FormField>
          <FormField label="Entity">
            <Input
              required
              value={meta.entity}
              onChange={(e) => setMeta({ ...meta, entity: e.target.value })}
            />
          </FormField>
        </div>
        <FormField label="Primary description">
          <Input
            required
            value={meta.primaryDesc}
            onChange={(e) => setMeta({ ...meta, primaryDesc: e.target.value })}
            data-testid="kn-create-desc"
          />
        </FormField>
        <div className="grid grid-cols-2 gap-3">
          <FormField label="Kind" hint="e.g., 10-K, pillar3, policy">
            <Input
              value={meta.kind}
              onChange={(e) => setMeta({ ...meta, kind: e.target.value })}
            />
          </FormField>
          <FormField label="Effective date" hint="ISO date">
            <Input
              type="date"
              value={meta.effectiveDate}
              onChange={(e) => setMeta({ ...meta, effectiveDate: e.target.value })}
            />
          </FormField>
        </div>
        <FormField label="Tags" hint="Comma-separated">
          <Input
            value={meta.tags}
            onChange={(e) => setMeta({ ...meta, tags: e.target.value })}
          />
        </FormField>

        {stage === "uploading" && (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-bny-mist" data-testid="kn-upload-progress">
            <div
              className="h-full bg-bny-teal transition-[width]"
              style={{ width: `${Math.max(2, putProgress * 100)}%` }}
            />
          </div>
        )}

        {error && (
          <div role="alert" className="text-xs text-bny-danger mt-3" data-testid="kn-create-error">
            {error}
          </div>
        )}
        <div className="flex items-center justify-end gap-2 mt-4">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton
            type="submit"
            disabled={busy || !file || !docHash}
            testId="kn-create-submit"
          >
            {stageLabel[stage]}
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
  <td className={`px-3 py-2 align-middle ${className}`}>{children}</td>
);
