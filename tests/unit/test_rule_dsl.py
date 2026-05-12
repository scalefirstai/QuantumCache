"""
Unit tests for the rule-engine DSL — core/domain/rules.py.

Covers leaf ops, nested all/any/not, age_days_gt, regex matches, dotted
path access, type coercion, malformed inputs, and verdict interpolation.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.domain.rules import (
    Rule, apply_rules, bump_version, evaluate, get_path, interpolate,
    validate_condition, validate_rule,
)


# ── get_path ───────────────────────────────────────────────────────

def test_get_path_dotted_dict():
    assert get_path({"a": {"b": {"c": 1}}}, "a.b.c") == 1


def test_get_path_list_index():
    assert get_path({"xs": [{"x": 9}, {"x": 10}]}, "xs.1.x") == 10


def test_get_path_missing_returns_none():
    assert get_path({"a": 1}, "missing") is None
    assert get_path({"a": 1}, "a.b.c") is None
    assert get_path(None, "a") is None


def test_get_path_attribute_fallback():
    class Obj:
        x = 7
    assert get_path(Obj(), "x") == 7


# ── leaf operators ─────────────────────────────────────────────────

def _eval(when, ctx, today=None):
    return evaluate(when, ctx, today)


def test_eq_ne():
    assert _eval({"field": "a", "op": "eq", "value": 1}, {"a": 1})
    assert not _eval({"field": "a", "op": "eq", "value": 2}, {"a": 1})
    assert _eval({"field": "a", "op": "ne", "value": 2}, {"a": 1})


def test_lt_lte_gt_gte():
    assert _eval({"field": "a", "op": "lt", "value": 2}, {"a": 1})
    assert _eval({"field": "a", "op": "lte", "value": 1}, {"a": 1})
    assert _eval({"field": "a", "op": "gt", "value": 0}, {"a": 1})
    assert _eval({"field": "a", "op": "gte", "value": 1}, {"a": 1})
    # Type-coerced strings
    assert _eval({"field": "a", "op": "lt", "value": 2}, {"a": "1.5"})
    # Mismatched types
    assert not _eval({"field": "a", "op": "lt", "value": 2}, {"a": "abc"})


def test_in_not_in():
    assert _eval({"field": "a", "op": "in", "value": [1, 2, 3]}, {"a": 2})
    assert _eval({"field": "a", "op": "not_in", "value": [1, 2]}, {"a": 5})


def test_contains_on_list_and_string():
    assert _eval({"field": "tags", "op": "contains", "value": "bootstrap"}, {"tags": ["bootstrap", "x"]})
    assert _eval({"field": "doc_id", "op": "contains", "value": "pillar3"}, {"doc_id": "bny-2024q3-pillar3"})
    assert not _eval({"field": "tags", "op": "contains", "value": "missing"}, {"tags": ["x"]})


def test_matches_regex():
    assert _eval({"field": "doc_id", "op": "matches", "value": r"\d{4}q[1-4]"}, {"doc_id": "bny-2024q3-pillar3"})
    assert not _eval({"field": "doc_id", "op": "matches", "value": r"^foo"}, {"doc_id": "bar"})


def test_startswith_endswith():
    assert _eval({"field": "id", "op": "startswith", "value": "canon."}, {"id": "canon.is"})
    assert _eval({"field": "id", "op": "endswith", "value": ".is"}, {"id": "canon.is"})


def test_age_days_gt():
    today = dt.date(2026, 5, 12)
    # 30 days ago
    yesterday_iso = (today - dt.timedelta(days=30)).isoformat()
    assert _eval({"field": "d", "op": "age_days_gt", "value": 7}, {"d": yesterday_iso}, today)
    assert not _eval({"field": "d", "op": "age_days_gt", "value": 60}, {"d": yesterday_iso}, today)


def test_exists_and_truthy():
    assert _eval({"field": "a", "op": "exists"}, {"a": 0})
    assert not _eval({"field": "a", "op": "exists"}, {})
    assert _eval({"field": "a", "op": "truthy"}, {"a": "x"})
    assert not _eval({"field": "a", "op": "truthy"}, {"a": 0})


# ── composite conditions ───────────────────────────────────────────

def test_all_any_not():
    ctx = {"a": 1, "b": 2}
    assert _eval({"all": [
        {"field": "a", "op": "eq", "value": 1},
        {"field": "b", "op": "eq", "value": 2},
    ]}, ctx)
    assert not _eval({"all": [
        {"field": "a", "op": "eq", "value": 1},
        {"field": "b", "op": "eq", "value": 99},
    ]}, ctx)
    assert _eval({"any": [
        {"field": "a", "op": "eq", "value": 0},
        {"field": "b", "op": "eq", "value": 2},
    ]}, ctx)
    assert _eval({"not": {"field": "a", "op": "eq", "value": 99}}, ctx)


def test_empty_dict_is_vacuously_true():
    assert _eval({}, {"a": 1})


def test_nested_composites():
    when = {
        "all": [
            {"field": "tier", "op": "eq", "value": 1},
            {"any": [
                {"field": "name", "op": "matches", "value": "^canon\\.(reg|is)$"},
                {"field": "do_not_answer", "op": "truthy"},
            ]},
        ]
    }
    assert _eval(when, {"tier": 1, "name": "canon.is", "do_not_answer": False})
    assert not _eval(when, {"tier": 2, "name": "canon.is", "do_not_answer": False})


# ── interpolation ──────────────────────────────────────────────────

def test_interpolate_template():
    out = interpolate("entry {library_entry.id} expired on {library_entry.expiry_date}",
                      {"library_entry": {"id": "lib_x", "expiry_date": "2026-01-01"}})
    assert out == "entry lib_x expired on 2026-01-01"


def test_interpolate_missing_renders_question_mark():
    assert interpolate("hi {missing}", {}) == "hi ?"


# ── apply_rules ────────────────────────────────────────────────────

def _make_rule(rule_id, when, then, *, priority=100, engine="freshness"):
    return Rule(
        rule_id=rule_id, engine=engine, title="t", description="",
        priority=priority, status="active", version="1.0.0",
        when=when, then=then, review_queue="ops", tags=[],
    )


def test_apply_rules_returns_all_matching_in_priority_order():
    rules = [
        _make_rule("r.low", {"field": "x", "op": "eq", "value": 1}, {"stale": True, "reason": "low"}, priority=200),
        _make_rule("r.high", {"field": "x", "op": "eq", "value": 1}, {"stale": True, "reason": "high"}, priority=50),
    ]
    fired = apply_rules(rules, {"x": 1})
    assert [f.rule.rule_id for f in fired] == ["r.high", "r.low"]


def test_apply_rules_first_match_only_stops_early():
    rules = [
        _make_rule("a", {}, {"route": "halt"}, priority=10),
        _make_rule("b", {}, {"route": "auto_approve"}, priority=20),
    ]
    fired = apply_rules(rules, {}, first_match_only=True)
    assert len(fired) == 1
    assert fired[0].rule.rule_id == "a"


def test_apply_rules_skips_malformed():
    rules = [
        _make_rule("malformed", {"field": "x", "op": "no_such_op", "value": 1}, {"stale": True, "reason": "x"}),
        _make_rule("ok", {"field": "x", "op": "eq", "value": 1}, {"stale": True, "reason": "ok"}),
    ]
    fired = apply_rules(rules, {"x": 1})
    assert len(fired) == 1
    assert fired[0].rule.rule_id == "ok"


def test_apply_rules_interpolates_verdict():
    r = _make_rule("r", {}, {"reason": "got {x}"})
    fired = apply_rules([r], {"x": 42})
    assert fired[0].verdict["reason"] == "got 42"


# ── validation ─────────────────────────────────────────────────────

def test_validate_condition_empty_is_valid():
    assert validate_condition({}) == []


def test_validate_condition_unknown_op_flagged():
    errors = validate_condition({"field": "x", "op": "bogus", "value": 1})
    assert any("unknown op" in e["msg"] for e in errors)


def test_validate_condition_missing_field_flagged():
    errors = validate_condition({"op": "eq", "value": 1})
    assert any("missing 'field'" in e["msg"] for e in errors)


def test_validate_condition_invalid_regex_flagged():
    errors = validate_condition({"field": "x", "op": "matches", "value": "[unbalanced"})
    assert any("invalid regex" in e["msg"] for e in errors)


def test_validate_rule_engine_check():
    r = _make_rule("r", {}, {"stale": True})
    r.engine = "bogus"  # type: ignore[assignment]
    errors = validate_rule(r)
    assert any(e["path"] == "engine" for e in errors)


def test_validate_rule_approval_unknown_route():
    r = _make_rule("r", {}, {"route": "weird"}, engine="approval")
    errors = validate_rule(r)
    assert any(e["path"] == "then.route" for e in errors)


# ── version bumping ───────────────────────────────────────────────

def test_bump_version_minor():
    assert bump_version("1.0.0") == "1.1.0"
    assert bump_version("1.2.5") == "1.3.0"


def test_bump_version_major_patch():
    assert bump_version("1.2.3", level="major") == "2.0.0"
    assert bump_version("1.2.3", level="patch") == "1.2.4"


def test_bump_version_invalid_returns_default():
    assert bump_version("garbage") == "1.0.0"
