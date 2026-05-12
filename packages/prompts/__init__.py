"""
Active-prompt loader for L06 agents.

Each agent's source-of-truth lives at:

    services/<svc>/prompts/v<semver>.md       # versioned files
    services/<svc>/prompts/active.txt         # one line: active version

The AutoGen Lite API gateway writes new version files and updates
active.txt. Each agent calls `resolve_active(__file__)` at startup
(or per-request when the dev wants hot-reload) to get the path to the
right prompt file. If `active.txt` is missing, falls back to v1.0.0.md
so existing agents that haven't been touched still work.

Returns a `ResolvedPrompt` with the path *and* the resolved version
string so the agent can stamp the version into its journal event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)\.md$")


@dataclass(frozen=True)
class ResolvedPrompt:
    path: Path
    version: str


def _semver_key(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def resolve_active(service_module_file: str) -> ResolvedPrompt:
    """Given an agent's `__file__`, return the active prompt path + version.

    The agent layout is `services/<svc>/agent.py` and prompts live at
    `services/<svc>/prompts/`.
    """
    svc_dir = Path(service_module_file).resolve().parent
    prompts_dir = svc_dir / "prompts"

    # Prefer active.txt.
    active_marker = prompts_dir / "active.txt"
    if active_marker.exists():
        version = active_marker.read_text(encoding="utf-8").strip()
        candidate = prompts_dir / f"v{version}.md"
        if candidate.exists():
            return ResolvedPrompt(path=candidate, version=version)
        # Marker points to a missing file — fall through to "highest existing".

    # Highest existing version (defensive default).
    versions = []
    for p in prompts_dir.iterdir() if prompts_dir.exists() else []:
        m = _SEMVER_RE.match(p.name)
        if m:
            versions.append(p)
    if not versions:
        raise FileNotFoundError(f"no prompt files in {prompts_dir}")
    versions.sort(key=lambda p: _semver_key(p.stem.lstrip("v")))
    chosen = versions[-1]
    return ResolvedPrompt(path=chosen, version=chosen.stem.lstrip("v"))
