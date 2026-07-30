"""LGC viability has ONE definition. These tests are what enforce that.

There are three renderings of the rule, in three media, and they cannot share a single
artifact:

  1. ``use_verdicts.lgc_verdict_sql``            — the SQL definition (board scoring)
  2. ``precompute_needles._LGC_VIABLE``          — generated from (1), needle metric
  3. ``candidate_search._LGC_EFFECTIVE_LABEL``   — SQLAlchemy ORM case(), display path

(2) is now GENERATED from (1), so it cannot drift. (3) is a different medium — an ORM
``case()`` cannot consume a SQL string — so nothing structural keeps it aligned, and a
comment asking for it demonstrably does not: ``_LGC_VIABLE`` carried "Matches
services/use_verdicts._LGC_VERDICT_SQL — keep in sync" while omitting the QC veto
entirely. That drift made the needle metric count 6,702 phantom LGC needles in
Montgomery County MD alone (AR Agricultural Reserve + RC Rural Cluster, where a human had
marked self_storage AND mini_warehouse prohibited), against a 17,096 baseline.

So the ORM twin is pinned by a TRUTH TABLE over every combination of
(self_storage x mini_warehouse x light_industrial x human_reviewed) instead of by a
request in a comment.
"""
from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

import pytest

# scripts/ is not a package and is not on the path under pytest; the needle predicate
# lives there and is part of what these tests pin.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from app.services.use_verdicts import (
    LGC_SLUG,
    lgc_verdict_sql,
    verdict_expr,
)

_PERMS: tuple[str | None, ...] = (
    None, "permitted", "conditional", "prohibited", "unclear",
)


def _lgc_rule(ss: str | None, mw: str | None, li: str | None,
              human_reviewed: bool) -> str | None:
    """The rule in plain Python — the reference the three renderings must match.

    Deliberately written from the ordinance intent rather than transliterated from any
    one implementation, so it can disagree with all of them.
    """
    if ss is None and mw is None and li is None:
        return None                                    # ungrounded, not prohibited
    if ss == "prohibited" and human_reviewed and li != "permitted":
        return "prohibited"                            # QC veto (Brink Rd)
    if ss == "permitted" or mw == "permitted":
        return "permitted"
    if ss == "conditional" or mw == "conditional" or li in ("permitted", "conditional"):
        return "conditional"
    if "unclear" in (ss, mw, li):
        return "unclear"
    return "prohibited"


ALL_CASES = list(itertools.product(_PERMS, _PERMS, _PERMS, (True, False)))


def test_truth_table_is_exhaustive() -> None:
    """A guard on the guard: 5*5*5*2 combinations, or the sweep has silently shrunk."""
    assert len(ALL_CASES) == 250


@pytest.mark.parametrize("case", ALL_CASES)
def test_orm_twin_matches_the_shared_rule(case) -> None:
    """candidate_search._LGC_EFFECTIVE_LABEL must agree with the shared rule.

    Evaluated by walking the ORM case()'s whens in order, which is how SQL evaluates it.
    'unclassified' is the ORM's label for the NULL/ungrounded branch that the SQL
    definition expresses as NULL — the only intentional difference between them.
    """
    from app.models.zone_use_matrix import UsePermission
    from app.services.candidate_search import _LGC_EFFECTIVE_LABEL

    ss, mw, li, hr = case
    expected = _lgc_rule(ss, mw, li, hr)

    def val(name: str | None):
        return None if name is None else UsePermission(name)

    row = {"self_storage": val(ss), "mini_warehouse": val(mw),
           "light_industrial": val(li), "human_reviewed": hr}
    got = _eval_orm_case(_LGC_EFFECTIVE_LABEL, row)
    if expected is None:
        assert got == "unclassified", (
            f"{case}: ORM twin returned {got!r}; the ungrounded branch must stay "
            f"distinct from a determined 'prohibited'")
    else:
        assert got == expected, f"{case}: ORM twin {got!r} != shared rule {expected!r}"


def _eval_orm_case(expr, row: dict):
    """Evaluate a SQLAlchemy case() against a plain dict, in clause order."""
    from sqlalchemy.sql.elements import Case
    assert isinstance(expr, Case)
    for cond, result in expr.whens:
        if _eval_clause(cond, row):
            return result.value
    return expr.else_.value if expr.else_ is not None else None


def _eval_clause(clause, row: dict) -> bool:
    """Minimal evaluator for the and_/or_/==/is_/is_distinct_from shapes used here."""
    from sqlalchemy.sql.elements import (
        BinaryExpression,
        BooleanClauseList,
        Grouping,
    )

    # SQLAlchemy wraps nested and_/or_ in Grouping (the parenthesisation node).
    while isinstance(clause, Grouping):
        clause = clause.element
    if isinstance(clause, BooleanClauseList):
        op = clause.operator.__name__
        parts = [_eval_clause(c, row) for c in clause.clauses]
        return all(parts) if "and" in op else any(parts)
    if isinstance(clause, BinaryExpression):
        from sqlalchemy.sql.elements import False_, True_

        col = getattr(clause.left, "key", None) or getattr(clause.left, "name", None)
        left = row.get(col)
        # `col IS true` renders the RHS as SQLAlchemy's True_() singleton, which has NO
        # .value. Reading .value there yielded None, so `True is None` was False and the
        # QC-veto branch evaluated false for EVERY row -- the harness silently disabled
        # the branch it exists to test, and reported 16 mismatches against a correct
        # implementation. Resolve the singletons explicitly.
        if isinstance(clause.right, True_):
            right = True
        elif isinstance(clause.right, False_):
            right = False
        else:
            right = getattr(clause.right, "value", None)
        op = clause.operator.__name__
        if op in ("is_", "is_"):
            return left is right
        if op == "isnot" or op == "is_not":
            return left is not right
        if op == "eq":
            return left == right
        if op == "is_distinct_from":
            return left != right
        if op == "isnot_distinct_from":
            return left == right
        raise AssertionError(f"unhandled operator {op!r} — extend the evaluator")
    raise AssertionError(f"unhandled clause {type(clause).__name__}")


def test_needle_metric_is_generated_not_copied() -> None:
    """The needle predicate must be BUILT from the shared function, veto included."""
    from precompute_needles import _LGC_VIABLE

    assert "IS DISTINCT FROM 'permitted'" in _LGC_VIABLE, (
        "the QC veto is missing from the needle predicate — this is exactly the drift "
        "that produced 6,702 phantom Montgomery MD needles")
    assert "v.ss" in _LGC_VIABLE and "v.hr" in _LGC_VIABLE
    # human_reviewed must be the real column, not a hardcoded literal that only happens
    # to agree because of how the LATERAL is written today.
    assert "'true'" not in _LGC_VIABLE and " true " not in _LGC_VIABLE


def test_needle_lateral_still_filters_human_reviewed() -> None:
    """Pins the property the metric's correctness used to rest on IMPLICITLY.

    Even though the veto now receives the real human_reviewed column, the LATERAL's
    filter is load-bearing for the rest of the needle definition (an un-reviewed matrix
    row must not ground a needle at all). Assert it rather than assume it.
    """
    from precompute_needles import _LATERAL

    assert re.search(r"AND\s+m\.human_reviewed", _LATERAL), (
        "the needle LATERAL no longer restricts to human-reviewed matrix rows")
    assert "human_reviewed AS hr" in _LATERAL or "m.human_reviewed AS hr" in _LATERAL


def test_board_expression_still_carries_the_veto() -> None:
    expr = verdict_expr(LGC_SLUG)
    assert "IS DISTINCT FROM 'permitted'" in expr
    assert "zum.human_reviewed" in expr


def test_shared_builder_renders_over_arbitrary_aliases() -> None:
    """The whole point of the refactor: one implementation, many renderings."""
    out = lgc_verdict_sql("a.x", "a.y", "a.z", "a.hr")
    for tok in ("a.x", "a.y", "a.z", "a.hr"):
        assert tok in out
    assert "zum." not in out
