"""
Filesystem-backed PromptsRepository.

Layout under each agent's directory:

    services/<agent_id>/prompts/
        v1.0.0.md          # original
        v1.0.1.md          # created by API
        ...
        active.txt         # single line, holds the active version string
        audit.jsonl        # append-only audit log

Writes are atomic: temp-file + os.replace. Audit entries are append-only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from core.ports.prompts import (
    AuditEntry,
    PromptDocument,
    PromptsRepository,
    VersionConflict,
    VersionSummary,
)


# Agents that are LLM-backed and have prompts; the order matches the
# L06 roster order in the spec.
LLM_AGENTS: dict[str, dict] = {
    "classifier":  {"name": "QuestionMapper",     "description": "Maps a framework question to a canonical_id with confidence.",
                    "default_tools": ["taxonomy.classify", "embedding.search"]},
    "retrieval":   {"name": "EvidenceSourcer",    "description": "Produces an evidence bundle from the BNY corpus; never drafts prose.",
                    "default_tools": ["library.lookup", "retrieval.hybrid"]},
    "drafter":     {"name": "DraftComposer",      "description": "Drafts the response from evidence + library entry; cites every claim.",
                    "default_tools": ["llm.complete", "prompt.registry"]},
    "validator":   {"name": "CitationVerifier",   "description": "Verifies every cited span resolves and that the draft is supported.",
                    "default_tools": ["corpus.fetch_span", "hash.verify"]},
    "consistency": {"name": "ConsistencyChecker", "description": "Compares the draft against recent shipped responses for the same canonical.",
                    "default_tools": ["duckdb.query", "embedding.similarity"]},
    "pii":         {"name": "PiiScrubber",        "description": "Detects PII / internal refs / client commercials in the draft.",
                    "default_tools": ["presidio.analyze", "regex.recognizer"]},
}

RULE_AGENTS: dict[str, dict] = {
    "freshness":   {"name": "FreshnessAuditor",   "description": "Rule-based: flags stale evidence and library entries.",
                    "default_tools": ["library.expiry", "corpus.freshness"]},
    "router":      {"name": "ApprovalRouter",     "description": "Rule-based: routes to the right SME queue by domain + tier.",
                    "default_tools": ["opa.evaluate", "queue.enqueue"]},
}


_SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.md$")


def _semver_key(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def _bump(version: str, kind: str) -> str:
    major, minor, patch = _semver_key(version)
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor += 1
        patch = 0
    elif kind == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"unknown bump kind: {kind}")
    return f"{major}.{minor}.{patch}"


def _split_body(raw: str) -> tuple[dict, str, str]:
    """Returns (frontmatter_dict, system_text, user_template_text)."""
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError("missing YAML frontmatter")
    fm_text = parts[1]
    body = parts[2]
    frontmatter: dict = {}
    for line in fm_text.strip().splitlines():
        if not line.strip() or ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        # Strip surrounding quotes from scalar values; preserve list syntax.
        if v.startswith("[") and v.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
            frontmatter[k.strip()] = items
        else:
            frontmatter[k.strip()] = v.strip('"').strip("'")
    # Body has "# System\n...\n# User\n..."
    if "# User" not in body:
        raise ValueError("prompt body missing '# User' section")
    system_part, user_part = body.split("# User", 1)
    system_part = system_part.replace("# System", "").strip()
    user_part = user_part.strip()
    return frontmatter, system_part, user_part


def _render(frontmatter: dict, system: str, user_template: str) -> str:
    """Round-trips the .md file: frontmatter ---, # System, # User."""
    lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            inner = ", ".join(f'"{x}"' for x in v)
            lines.append(f"{k}: [{inner}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("# System")
    lines.append("")
    lines.append(system.strip())
    lines.append("")
    lines.append("# User")
    lines.append("")
    lines.append(user_template.strip())
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` via temp-file + rename so readers never
    see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=str(path.parent), delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, path)


def _append_audit(audit_path: Path, entry: AuditEntry) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": entry.ts, "actor": entry.actor, "action": entry.action,
        "from_version": entry.from_version, "to_version": entry.to_version,
        "comment": entry.comment,
    }
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


class FsPrompts:
    def __init__(self, services_root: Path) -> None:
        self._root = services_root

    # ---- helpers ----

    def _svc_dir(self, agent_id: str) -> Path:
        return self._root / agent_id / "prompts"

    def _version_files(self, agent_id: str) -> list[Path]:
        d = self._svc_dir(agent_id)
        if not d.exists():
            return []
        files = []
        for p in d.iterdir():
            m = _SEMVER_RE.match(p.name)
            if m:
                files.append(p)
        files.sort(key=lambda p: _semver_key(p.stem.lstrip("v")))
        return files

    def _active_path(self, agent_id: str) -> Path:
        return self._svc_dir(agent_id) / "active.txt"

    def _audit_path(self, agent_id: str) -> Path:
        return self._svc_dir(agent_id) / "audit.jsonl"

    def _resolve_active(self, agent_id: str) -> Optional[str]:
        ap = self._active_path(agent_id)
        if ap.exists():
            return ap.read_text(encoding="utf-8").strip() or None
        files = self._version_files(agent_id)
        if not files:
            return None
        # Default to highest existing version.
        return files[-1].stem.lstrip("v")

    def _version_path(self, agent_id: str, version: str) -> Path:
        return self._svc_dir(agent_id) / f"v{version}.md"

    def _load_doc(self, agent_id: str, version: str) -> PromptDocument:
        path = self._version_path(agent_id, version)
        raw = path.read_text(encoding="utf-8")
        frontmatter, system, user_template = _split_body(raw)
        meta = LLM_AGENTS.get(agent_id, {})
        tools = frontmatter.get("tools") or meta.get("default_tools", [])
        if not isinstance(tools, list):
            tools = [str(tools)]
        return PromptDocument(
            agent_id=agent_id,
            agent_name=frontmatter.get("agent", meta.get("name", agent_id)),
            version=version,
            model=frontmatter.get("model", "claude-sonnet-4-6"),
            temperature=float(frontmatter.get("temperature", "0.2")),
            max_tokens=int(frontmatter.get("max_tokens", "1024")),
            description=frontmatter.get("description", meta.get("description", "")),
            tools=tuple(tools),
            system=system,
            user_template=user_template,
            raw=raw,
            sha256="sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )

    # ---- PromptsRepository surface ----

    def list_agent_ids(self) -> list[str]:
        # Return LLM agents first, then rule-based; preserves spec ordering.
        return list(LLM_AGENTS) + list(RULE_AGENTS)

    def get_document(self, agent_id: str, version: Optional[str] = None) -> Optional[PromptDocument]:
        if agent_id not in LLM_AGENTS:
            return None
        v = version or self._resolve_active(agent_id)
        if v is None:
            return None
        if not self._version_path(agent_id, v).exists():
            return None
        return self._load_doc(agent_id, v)

    def list_versions(self, agent_id: str) -> list[VersionSummary]:
        if agent_id not in LLM_AGENTS:
            return []
        active = self._resolve_active(agent_id)
        # Index of "create" audit entries → comment.
        create_comments: dict[str, str] = {}
        for entry in self.list_audit(agent_id):
            if entry.action == "create" and entry.comment:
                create_comments[entry.to_version] = entry.comment
        out = []
        for p in self._version_files(agent_id):
            v = p.stem.lstrip("v")
            ctime = dt.datetime.fromtimestamp(p.stat().st_ctime, tz=dt.timezone.utc).isoformat()
            content = p.read_text(encoding="utf-8")
            out.append(VersionSummary(
                version=v,
                created_at=ctime,
                is_active=(v == active),
                sha256="sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
                comment=create_comments.get(v),
            ))
        return out

    def active_version(self, agent_id: str) -> Optional[str]:
        if agent_id not in LLM_AGENTS:
            return None
        return self._resolve_active(agent_id)

    def create_version(
        self,
        agent_id: str,
        base_version: str,
        bump: str,
        system: str,
        user_template: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        description: Optional[str] = None,
        tools: Optional[list[str]] = None,
        actor: str = "unknown",
        comment: Optional[str] = None,
        activate: bool = False,
        action_label: str = "create",
    ) -> PromptDocument:
        if agent_id not in LLM_AGENTS:
            raise KeyError(agent_id)
        current = self._resolve_active(agent_id)
        if current is None:
            raise FileNotFoundError(f"no active version to base on for {agent_id}")
        if base_version != current:
            raise VersionConflict(current_active=current, expected=base_version)
        new_version = _bump(current, bump)
        new_path = self._version_path(agent_id, new_version)
        if new_path.exists():
            raise VersionConflict(current_active=current, expected=base_version)

        # Carry the existing frontmatter forward unless caller overrides.
        base_doc = self._load_doc(agent_id, current)
        fm: dict = {
            "agent": base_doc.agent_name,
            "version": new_version,
            "model": model or base_doc.model,
            "temperature": str(temperature if temperature is not None else base_doc.temperature),
            "max_tokens": str(max_tokens if max_tokens is not None else base_doc.max_tokens),
            "description": description if description is not None else base_doc.description,
            "tools": list(tools) if tools is not None else list(base_doc.tools),
        }
        rendered = _render(fm, system, user_template)
        _atomic_write(new_path, rendered)
        _append_audit(self._audit_path(agent_id), AuditEntry(
            ts=dt.datetime.now(dt.timezone.utc).isoformat(),
            actor=actor, action=action_label,
            from_version=current, to_version=new_version, comment=comment,
        ))
        if activate:
            # Bypass set_active's "already current?" short-circuit — we just
            # wrote the new file, so its resolve would lie about the prior
            # state. Write active.txt + audit directly using `current` we
            # captured before creating the new version.
            _atomic_write(self._active_path(agent_id), new_version + "\n")
            _append_audit(self._audit_path(agent_id), AuditEntry(
                ts=dt.datetime.now(dt.timezone.utc).isoformat(),
                actor=actor, action="activate",
                from_version=current, to_version=new_version, comment=comment,
            ))
        return self._load_doc(agent_id, new_version)

    def set_active(
        self,
        agent_id: str,
        version: str,
        actor: str,
        comment: Optional[str],
    ) -> Optional[str]:
        if agent_id not in LLM_AGENTS:
            raise KeyError(agent_id)
        if not self._version_path(agent_id, version).exists():
            raise FileNotFoundError(f"version {version} not found for {agent_id}")
        current = self._resolve_active(agent_id)
        if current == version:
            return current
        _atomic_write(self._active_path(agent_id), version + "\n")
        _append_audit(self._audit_path(agent_id), AuditEntry(
            ts=dt.datetime.now(dt.timezone.utc).isoformat(),
            actor=actor, action="activate",
            from_version=current, to_version=version, comment=comment,
        ))
        return current

    def list_audit(self, agent_id: str) -> list[AuditEntry]:
        ap = self._audit_path(agent_id)
        if not ap.exists():
            return []
        entries: list[AuditEntry] = []
        with ap.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                entries.append(AuditEntry(
                    ts=rec["ts"], actor=rec["actor"], action=rec["action"],
                    from_version=rec.get("from_version"),
                    to_version=rec["to_version"],
                    comment=rec.get("comment"),
                ))
        entries.sort(key=lambda e: e.ts, reverse=True)
        return entries
