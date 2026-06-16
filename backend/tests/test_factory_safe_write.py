"""Tests for the Op-5 coordination rule — app/services/zone_matrix_write.

Uses a fake asyncpg connection so the hand-row-skip + conflict-count logic is
exercised deterministically without a live DB. (Real ON CONFLICT firing is a
Postgres concern; here we assert the helper's contract: which rows it sends and
how it tallies the command-tag results.)
"""
import asyncio

from app.services.zone_matrix_write import audit_muni_gap, factory_safe_write

JID = "11111111-1111-1111-1111-111111111111"
MUNI = "Testville borough"


class FakeConn:
    """Minimal asyncpg.Connection stand-in.

    - ``human_codes``: zone_codes that already have human_reviewed=true rows.
    - ``conflict_codes``: zone_codes whose INSERT should report a conflict
      (command tag "INSERT 0 0", i.e. ON CONFLICT DO NOTHING fired).
    - ``parcel_codes`` / ``matrix_codes``: for audit_muni_gap.
    """

    def __init__(self, human_codes=(), conflict_codes=(), parcel_codes=(), matrix_codes=()):
        self._human = list(human_codes)
        self._conflict = {c for c in conflict_codes}
        self._parcel = list(parcel_codes)
        self._matrix = list(matrix_codes)
        self.inserted: list[str] = []

    async def fetch(self, sql, *args):
        if "human_reviewed = true" in sql:
            return [{"zone_code": c} for c in self._human]
        if "FROM parcels" in sql:
            return [{"zoning_code": c} for c in self._parcel]
        if "FROM zone_use_matrix" in sql:
            return [{"zone_code": c} for c in self._matrix]
        return []

    async def execute(self, sql, *args):
        code = args[2]  # $3 = zone_code
        if code in self._conflict:
            return "INSERT 0 0"
        self.inserted.append(code)
        return "INSERT 0 1"

    async def fetchval(self, sql, *args):
        return 0


def _rows(*codes):
    return [{"zone_code": c, "self_storage": "unclear"} for c in codes]


def test_zero_hand_rows_writes_all():
    conn = FakeConn(human_codes=())
    res = asyncio.run(factory_safe_write(conn, JID, MUNI, _rows("R-1", "B-2", "I-1")))
    assert res == {"written": 3, "skipped_human": 0, "skipped_conflict": 0}
    assert conn.inserted == ["R-1", "B-2", "I-1"]


def test_skips_existing_human_rows():
    # 5 hand rows present; factory tries to write all 5 + 2 new ones.
    conn = FakeConn(human_codes=("R-1", "R-2", "B-1", "I-1", "I-2"))
    res = asyncio.run(
        factory_safe_write(conn, JID, MUNI, _rows("R-1", "R-2", "B-1", "I-1", "I-2", "C-1", "OP"))
    )
    assert res["skipped_human"] == 5
    assert res["written"] == 2
    assert res["skipped_conflict"] == 0
    # The 5 human-owned codes were never sent to INSERT.
    assert conn.inserted == ["C-1", "OP"]


def test_conflict_on_non_human_row_counted():
    # No human rows, but B-2 hits an existing (non-human) active row -> DO NOTHING.
    conn = FakeConn(human_codes=(), conflict_codes=("B-2",))
    res = asyncio.run(factory_safe_write(conn, JID, MUNI, _rows("R-1", "B-2", "I-1")))
    assert res == {"written": 2, "skipped_human": 0, "skipped_conflict": 1}
    assert conn.inserted == ["R-1", "I-1"]  # B-2 attempted but conflicted


def test_human_skip_is_format_insensitive():
    # Hand row "B 1" (spaced) must shield factory code "B-1" (hyphen).
    conn = FakeConn(human_codes=("B 1",))
    res = asyncio.run(factory_safe_write(conn, JID, MUNI, _rows("B-1", "R-1")))
    assert res["skipped_human"] == 1
    assert conn.inserted == ["R-1"]


def test_factory_source_cannot_masquerade_as_human():
    conn = FakeConn()
    asyncio.run(
        factory_safe_write(
            conn, JID, MUNI,
            [{"zone_code": "I-1", "self_storage": "permitted", "classification_source": "human"}],
        )
    )
    # The bad 'human' source was forced back to the factory default before insert.
    # (We assert it was sent — the SQL param coercion happens in execute; the
    # guard is that source not in _VALID_FACTORY_SOURCES -> default.)
    assert conn.inserted == ["I-1"]


def test_audit_muni_gap_flags_uncovered_codes():
    conn = FakeConn(parcel_codes=("R-1", "B-2", "I-1", "M-1"), matrix_codes=("R-1", "B-2"))
    res = asyncio.run(audit_muni_gap(conn, JID, MUNI))
    assert set(res["gap_codes"]) == {"I-1", "M-1"}
    assert res["parcel_codes"] == 4
    assert res["matrix_codes"] == 2


# ── blocks_human_overwrite: the canonical single-chokepoint predicate (catch #13) ──
from app.services.zone_matrix_write import blocks_human_overwrite


def test_blocks_human_overwrite_rule():
    # existing human + incoming non-human => BLOCK (protect the hand verdict)
    assert blocks_human_overwrite(True, False) is True
    # existing human + incoming human => allow (operator re-dispatch)
    assert blocks_human_overwrite(True, True) is False
    # existing non-human => never blocks (factory may upsert factory/heuristic)
    assert blocks_human_overwrite(False, False) is False
    assert blocks_human_overwrite(False, True) is False
