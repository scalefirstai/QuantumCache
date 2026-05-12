"""Rule engine domain model + DSL evaluator.

A `Rule` is a JSON-encoded predicate that drives one of the rule-based
agents in ddq.md §L06 (FreshnessAuditor, ApprovalRouter). The DSL is
deliberately small: a `Condition` tree (leaf | all | any | not) over a
flattened input context, paired with a `then` verdict.

The evaluator is pure — no I/O, no globals, no side effects. Adapters
in `infra/adapters/` are responsible for persistence; this module just
parses + evaluates.

Spec: docs/specs/rule-engine.md
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field, asdict
from functools import lru_cache
from typing import Any, Iterable, Literal, Optional, Union


# ────────────────────────────────────────────────────────────────────
# Types
# ────────────────────────────────────────────────────────────────────

RuleEngine = Literal["freshness", "approval"]
RuleStatus = Literal["draft", "pending_review", "active", "archived"]

# Operators supported by leaf predicates. Keep the surface small —
# expressiveness lives in nesting, not in operator count.
Op = Literal[
    "eq", "ne",
    "lt", "lte", "gt", "gte",
    "in", "not_in",
    "contains",
    "matches",          # re.search (regex)
    "startswith", "endswith",
    "age_days_gt",      # context value is ISO date; compare to today − value (days)
    "exists",           # truthy presence (value ignored)
    "truthy",           # explicit bool-cast check (value ignored)
]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class Rule:
    """One configurable rule. JSON-serializable; persisted as `<rule_id>.json`
    on disk and as a single Mongo document keyed by `rule_id`.

    `priority` is evaluated low-to-high (priority=10 runs before priority=50).

    `status` is the lifecycle state:
      - draft          → editable, not yet active. Not evaluated by engines.
      - pending_review → in an SME queue awaiting approve/reject.
      - active         → live; engines load these.
      - archived       → superseded by a newer version of the same rule_id stem.
    """

    rule_id: str
    engine: RuleEngine
    title: str
    description: str
    priority: int
    status: RuleStatus
    version: str                       # semver "1.0.0", bumped on every edit
    when: dict                         # Condition tree (see _eval_condition)
    then: dict                         # engine-specific verdict (see _verdict_for)
    review_queue: str                  # SME queue for approval routing
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    submitted_by: Optional[str] = None
    rationale: Optional[str] = None    # SME note from approve/reject

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Rule":
        return cls(
            rule_id=raw["rule_id"],
            engine=raw["engine"],
            title=raw.get("title", ""),
            description=raw.get("description", ""),
            priority=int(raw.get("priority", 100)),
            status=raw.get("status", "draft"),
            version=raw.get("version", "1.0.0"),
            when=dict(raw.get("when") or {}),
            then=dict(raw.get("then") or {}),
            review_queue=raw.get("review_queue", "ops"),
            tags=list(raw.get("tags", [])),
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
            approved_at=raw.get("approved_at"),
            approved_by=raw.get("approved_by"),
            submitted_by=raw.get("submitted_by"),
            rationale=raw.get("rationale"),
        )


@dataclass
class FiredRule:
    """A rule that evaluated to true for some context. Carries the
    interpolated verdict so the caller can fold/aggregate."""
    rule: Rule
    verdict: dict


# ────────────────────────────────────────────────────────────────────
# DSL — field path resolution
# ────────────────────────────────────────────────────────────────────

def get_path(context: Any, path: str) -> Any:
    """Resolve a dotted path on a nested dict/list. Returns None on miss.

    Examples:
      get_path({"a": {"b": 1}}, "a.b")           → 1
      get_path({"xs": [{"x": 9}]}, "xs.0.x")     → 9
      get_path({"a": 1}, "missing")              → None
    """
    cur: Any = context
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            # Attribute access fallback (e.g. Pydantic model).
            cur = getattr(cur, part, None)
    return cur


# ────────────────────────────────────────────────────────────────────
# DSL — leaf operator evaluation
# ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=256)
def _compile_regex(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def _parse_iso_date(s: Any) -> Optional[dt.date]:
    if not isinstance(s, str):
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _coerce_number(v: Any) -> Optional[float]:
    if isinstance(v, bool):  # bools are ints in Python; reject explicitly
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _eval_leaf(actual: Any, op: Op, expected: Any, today: Optional[dt.date]) -> bool:
    if op == "exists":
        return actual is not None
    if op == "truthy":
        return bool(actual)
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op in ("lt", "lte", "gt", "gte"):
        a = _coerce_number(actual)
        b = _coerce_number(expected)
        if a is None or b is None:
            return False
        return {
            "lt": a < b, "lte": a <= b,
            "gt": a > b, "gte": a >= b,
        }[op]
    if op == "in":
        try:
            return actual in expected
        except TypeError:
            return False
    if op == "not_in":
        try:
            return actual not in expected
        except TypeError:
            return False
    if op == "contains":
        # actual is a list/string; expected is the needle.
        if actual is None:
            return False
        try:
            return expected in actual
        except TypeError:
            return False
    if op == "matches":
        if actual is None or not isinstance(expected, str):
            return False
        return _compile_regex(expected).search(str(actual)) is not None
    if op == "startswith":
        return isinstance(actual, str) and actual.startswith(str(expected))
    if op == "endswith":
        return isinstance(actual, str) and actual.endswith(str(expected))
    if op == "age_days_gt":
        d = _parse_iso_date(actual)
        n = _coerce_number(expected)
        if d is None or n is None:
            return False
        ref = today or dt.date.today()
        return (ref - d).days > n
    raise ValueError(f"unknown op: {op!r}")


# ────────────────────────────────────────────────────────────────────
# DSL — recursive condition evaluation
# ────────────────────────────────────────────────────────────────────

def _eval_condition(condition: dict, context: dict, today: Optional[dt.date]) -> bool:
    """Evaluate a Condition node against a context.

    Composite forms:
      {"all": [c1, c2, ...]}        → all true
      {"any": [c1, c2, ...]}        → at least one true
      {"not": c}                    → negation
    Leaf form:
      {"field": "...", "op": "...", "value": ...}
    """
    if not isinstance(condition, dict):
        raise ValueError(f"condition must be a dict, got {type(condition).__name__}")
    if "all" in condition:
        children = condition["all"]
        if not isinstance(children, list):
            raise ValueError("'all' must be a list of conditions")
        return all(_eval_condition(c, context, today) for c in children)
    if "any" in condition:
        children = condition["any"]
        if not isinstance(children, list):
            raise ValueError("'any' must be a list of conditions")
        return any(_eval_condition(c, context, today) for c in children)
    if "not" in condition:
        return not _eval_condition(condition["not"], context, today)
    if "field" in condition and "op" in condition:
        actual = get_path(context, condition["field"])
        return _eval_leaf(actual, condition["op"], condition.get("value"), today)
    if not condition:
        # Empty dict = vacuously true. Useful as a placeholder for new rules.
        return True
    raise ValueError(f"unrecognized condition shape: {list(condition.keys())}")


def evaluate(condition: dict, context: dict, today: Optional[dt.date] = None) -> bool:
    """Public entry point. Wraps `_eval_condition` with type guards."""
    return _eval_condition(condition, context, today)


# ────────────────────────────────────────────────────────────────────
# Rule firing + verdict interpolation
# ────────────────────────────────────────────────────────────────────

_TEMPLATE_RE = re.compile(r"\{([A-Za-z0-9_.]+)\}")


def interpolate(template: str, context: dict) -> str:
    """Substitute `{dotted.path}` tokens with values from the context.

    Missing paths become "?" to avoid blowing up SME-facing error strings.
    """

    def repl(m: re.Match) -> str:
        v = get_path(context, m.group(1))
        return "?" if v is None else str(v)

    return _TEMPLATE_RE.sub(repl, template)


def _interpolate_verdict(then: dict, context: dict) -> dict:
    """Walk the `then` shape and interpolate any string leaves."""
    out: dict = {}
    for k, v in then.items():
        if isinstance(v, str):
            out[k] = interpolate(v, context)
        elif isinstance(v, list):
            out[k] = [interpolate(x, context) if isinstance(x, str) else x for x in v]
        else:
            out[k] = v
    return out


def apply_rules(
    rules: Iterable[Rule],
    context: dict,
    *,
    today: Optional[dt.date] = None,
    first_match_only: bool = False,
) -> list[FiredRule]:
    """Evaluate `rules` (sorted by priority ascending) against `context`.

    Returns the list of rules that fired, each paired with its interpolated
    verdict. If `first_match_only` is True, stops at the first hit (the
    ApprovalRouter style); otherwise returns all hits (the FreshnessAuditor
    style — multiple stale signals can accumulate).
    """
    sorted_rules = sorted(rules, key=lambda r: (r.priority, r.rule_id))
    fired: list[FiredRule] = []
    for r in sorted_rules:
        try:
            hit = _eval_condition(r.when, context, today)
        except ValueError:
            # Malformed rules are skipped silently; the /validate endpoint
            # surfaces them at edit time so they don't reach prod.
            continue
        if hit:
            fired.append(FiredRule(rule=r, verdict=_interpolate_verdict(r.then, context)))
            if first_match_only:
                break
    return fired


# ────────────────────────────────────────────────────────────────────
# Validation — used by /api/v1/rules/validate
# ────────────────────────────────────────────────────────────────────

_VALID_OPS = set(Op.__args__)  # type: ignore[attr-defined]


def validate_condition(condition: Any, path: str = "when") -> list[dict]:
    """Walk a Condition tree and return a list of structural errors.

    Each error: {"path": str, "msg": str}. Empty list = valid.
    """
    errors: list[dict] = []
    if not isinstance(condition, dict):
        return [{"path": path, "msg": f"must be a dict, got {type(condition).__name__}"}]
    if not condition:
        return errors  # vacuously valid
    if "all" in condition or "any" in condition:
        key = "all" if "all" in condition else "any"
        children = condition[key]
        if not isinstance(children, list):
            errors.append({"path": f"{path}.{key}", "msg": "must be a list"})
            return errors
        for i, c in enumerate(children):
            errors.extend(validate_condition(c, path=f"{path}.{key}[{i}]"))
        return errors
    if "not" in condition:
        return validate_condition(condition["not"], path=f"{path}.not")
    if "field" in condition or "op" in condition:
        if "field" not in condition:
            errors.append({"path": path, "msg": "leaf missing 'field'"})
        if "op" not in condition:
            errors.append({"path": path, "msg": "leaf missing 'op'"})
        elif condition["op"] not in _VALID_OPS:
            errors.append({
                "path": f"{path}.op",
                "msg": f"unknown op {condition['op']!r}; valid: {sorted(_VALID_OPS)}",
            })
        if condition.get("op") == "matches" and isinstance(condition.get("value"), str):
            try:
                re.compile(condition["value"])
            except re.error as e:
                errors.append({"path": f"{path}.value", "msg": f"invalid regex: {e}"})
        return errors
    errors.append({"path": path, "msg": f"unrecognized condition keys: {sorted(condition.keys())}"})
    return errors


def validate_rule(rule: Rule) -> list[dict]:
    """Surface structural errors on a Rule. Returns [] if valid."""
    errors: list[dict] = []
    if rule.engine not in ("freshness", "approval"):
        errors.append({"path": "engine", "msg": f"must be 'freshness' or 'approval', got {rule.engine!r}"})
    if rule.status not in ("draft", "pending_review", "active", "archived"):
        errors.append({"path": "status", "msg": f"unknown status {rule.status!r}"})
    errors.extend(validate_condition(rule.when, path="when"))
    # Engine-specific then validation
    if rule.engine == "freshness":
        if "stale" in rule.then and not isinstance(rule.then["stale"], bool):
            errors.append({"path": "then.stale", "msg": "must be a boolean"})
    elif rule.engine == "approval":
        route = rule.then.get("route")
        if route is not None and route not in ("auto_approve", "sme_queue", "halt", "legal_review"):
            errors.append({"path": "then.route", "msg": f"unknown route {route!r}"})
    return errors


# ────────────────────────────────────────────────────────────────────
# Version bump helper
# ────────────────────────────────────────────────────────────────────

def bump_version(current: str, *, level: Literal["major", "minor", "patch"] = "minor") -> str:
    """Semver bump. Used on every PUT to track edit history within a rule_id."""
    try:
        parts = [int(x) for x in current.split(".")]
        while len(parts) < 3:
            parts.append(0)
        major, minor, patch = parts[:3]
    except (ValueError, AttributeError):
        return "1.0.0"
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
