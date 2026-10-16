"""LGC needle gate reads parcel_keep_metrics; storage needles are untouched (Phase B)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import precompute_needles as pn  # noqa: E402
from app.services.wealth_gate import hv_exempt_sql  # noqa: E402


def test_storage_predicates_byte_identical():
    assert pn._STORAGE_VIABLE == "v.hr AND v.ss IN ('permitted','conditional')"
    assert pn._WEALTH == ("p.acres >= 1.5 AND (prm.median_home_value >= 475000 "
                          f"OR {hv_exempt_sql()}) AND prm.median_hhi >= 100000")
    assert pn._STORAGE_NEEDLE == f"{pn._STORAGE_VIABLE} AND {pn._WEALTH}"
    assert "pkm" not in pn._STORAGE_NEEDLE


def test_lgc_gate_prefers_keep_lane_and_falls_back_to_wealth():
    g = pn._LGC_GATE
    assert pn._KEEP_NEEDLE_LANES == "('edge_of_wealth','core')"
    assert "CASE WHEN pkm.keep_lane IS NOT NULL" in g
    assert "THEN pkm.keep_lane IN ('edge_of_wealth','core')" in g
    assert f"ELSE ({pn._WEALTH}) END" in g
    assert g.startswith("p.acres >= 1.5 AND ")
    assert "growth_corridor" not in g


def test_needles_sql_counts_storage_on_the_unchanged_predicate():
    sql = pn._NEEDLES_SQL
    assert f"count(*) FILTER (WHERE {pn._STORAGE_NEEDLE})" in sql
    assert f"count(*) FILTER (WHERE {pn._LGC_VIABLE} AND {pn._LGC_GATE})" in sql
    assert "LEFT JOIN parcel_keep_metrics pkm ON pkm.parcel_id = p.id" in sql
    assert "LEFT JOIN parcel_ring_metrics prm" in sql
    # The row scope admits the union of both gates (storage FILTER re-applies _WEALTH).
    assert f"(({pn._WEALTH}) OR pkm.keep_lane IN {pn._KEEP_NEEDLE_LANES})" in sql


def test_deals_sql_uses_same_gates():
    sql = pn._DEALS_SQL
    assert f"FILTER (WHERE {pn._STORAGE_NEEDLE})" in sql
    assert f"FILTER (WHERE {pn._LGC_VIABLE} AND {pn._LGC_GATE})" in sql
    assert "LEFT JOIN parcel_keep_metrics pkm" in sql


def test_no_colon_bind_tokens_in_needle_sql():
    """repair_dt10_rings runs _NEEDLES_SQL through SQLAlchemy text(); a stray
    colon-prefixed token would invent a phantom bind parameter."""
    from sqlalchemy import text

    assert text(pn._NEEDLES_SQL)._bindparams == {}


def test_verify_batch_3b_uses_the_shared_gate():
    src = (_SCRIPTS / "verify_batch.py").read_text(encoding="utf-8")
    assert "_LGC_GATE" in src and "parcel_keep_metrics pkm" in src
