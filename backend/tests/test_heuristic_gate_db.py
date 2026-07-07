"""
Cross-checks that the SQL gate expressions (lead_eligible_sql / gate_reason_sql)
produce the SAME verdict as the Python reference gate_verdict() on a real
Postgres with the real enum types (catch #49).

Includes the armed-pool invariant at the SQL layer: a human_reviewed row is
never gated, whatever its source/confidence/verdict.

SAFETY: commits + deletes rows, so it self-skips unless DATABASE_URL is a
local/CI test DB (never prod).
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.services.verdict_gate import gate_reason_sql, gate_verdict, lead_eligible_sql

_DBURL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    (not _DBURL) or ("supabase" in _DBURL) or ("pooler" in _DBURL),
    reason="gate DB tests run only against a local/CI test DB, never prod",
)

# (self_storage, classification_source, confidence, human_reviewed)
_CASES = [
    ("conditional", "human", 0.35, True),     # armed pool: kept despite low conf
    ("permitted", "human", None, True),        # armed pool
    ("conditional", "llm", 0.9, False),        # grounded llm: kept
    ("permitted", "op5_factory", 0.72, False), # grounded factory: kept
    ("conditional", "rule", 0.35, False),      # heuristic low-conf: gated
    ("permitted", "crosswalk", 0.8, False),    # heuristic decent-conf: gated
    ("unclear", "unclear", 0.35, False),       # heuristic unclear: gated
    ("conditional", "rule", 0.35, True),       # human_reviewed overrides heuristic src
]


async def test_sql_gate_matches_python_reference(db_session):
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :n, 'PA')"),
        {"id": jid, "n": f"Gate {jid}"},
    )
    for i, (ss, src, conf, hr) in enumerate(_CASES):
        # Raw SQL bypasses ORM Python-side defaults — supply every NOT NULL
        # use column explicitly (CI catch 2026-07-07).
        await db_session.execute(
            text(
                "INSERT INTO zone_use_matrix "
                "(jurisdiction_id, zone_code, self_storage, mini_warehouse, "
                " light_industrial, luxury_garage_condo, classification_source, "
                " confidence, human_reviewed) "
                "VALUES (:jid, :zc, CAST(:ss AS use_permission_enum), "
                " 'unclear', 'unclear', 'unclear', "
                " CAST(:src AS classification_source_enum), :conf, :hr)"
            ),
            {"jid": jid, "zc": f"Z{i}", "ss": ss, "src": src, "conf": conf, "hr": hr},
        )
    await db_session.commit()
    try:
        rows = await db_session.execute(
            text(
                f"SELECT zone_code, ({lead_eligible_sql('zum')}) AS lead_eligible, "
                f"({gate_reason_sql('zum')}) AS gate_reason "
                f"FROM zone_use_matrix zum WHERE jurisdiction_id = :jid ORDER BY zone_code"
            ),
            {"jid": jid},
        )
        by_code = {r.zone_code: r for r in rows}
        for i, (ss, src, conf, hr) in enumerate(_CASES):
            want_elig, want_reason = gate_verdict(
                self_storage=ss, classification_source=src, confidence=conf, human_reviewed=hr,
            )
            got = by_code[f"Z{i}"]
            assert got.lead_eligible == want_elig, (i, ss, src, conf, hr, "eligible")
            assert got.gate_reason == want_reason, (i, ss, src, conf, hr, "reason")
            # the armed-pool invariant, explicitly
            if hr:
                assert got.lead_eligible is True and got.gate_reason is None
    finally:
        await db_session.execute(
            text("DELETE FROM zone_use_matrix WHERE jurisdiction_id = :jid"), {"jid": jid}
        )
        await db_session.execute(text("DELETE FROM jurisdictions WHERE id = :jid"), {"jid": jid})
        await db_session.commit()
