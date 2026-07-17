"""Guards for the use-case verdict registry (services/use_verdicts.py).

The load-bearing invariant: the self_storage expression must stay byte-identical
to the historical scorer query, so making the scorer use-case-aware never
perturbs the live self_storage scores.
"""
from app.services.use_verdicts import (
    LGC_SLUG,
    SELF_STORAGE_SLUG,
    verdict_expr,
)


def test_self_storage_expr_is_byte_identical():
    # This exact string is what buybox_scoring's SELECT used before the
    # use-case refactor. If it ever changes, self_storage scores move — which
    # must be a deliberate, separately-reviewed decision, not an accident.
    assert verdict_expr(SELF_STORAGE_SLUG) == "zum.self_storage::text"


def test_unknown_and_none_fall_back_to_self_storage():
    assert verdict_expr(None) == "zum.self_storage::text"
    assert verdict_expr("not_a_real_use_case") == "zum.self_storage::text"


def test_lgc_expr_derives_from_all_three_sibling_columns():
    expr = verdict_expr(LGC_SLUG)
    # Encodes the owner's rule: warehouse/storage OR light industrial.
    assert "zum.self_storage" in expr
    assert "zum.mini_warehouse" in expr
    assert "zum.light_industrial" in expr
    # Never reads the gate-suppressed stored column.
    assert "luxury_garage_condo" not in expr
    # NULL guard first so a missing matrix row stays ungrounded, not prohibited.
    assert expr.lstrip().startswith("CASE")
    assert "IS NULL" in expr
