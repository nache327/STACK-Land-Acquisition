"""
SQL↔Python parity for the wealth gate (near-ring override rule): wealth_tag_sql
must produce the same tag as gate_wealth() on real Postgres, using the actual
Concord/Darby prod ring values.

SAFETY: commits + deletes; self-skips unless DATABASE_URL is a local/CI test DB.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.services.wealth_gate import gate_wealth, wealth_tag_sql

_DBURL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    (not _DBURL) or ("supabase" in _DBURL) or ("pooler" in _DBURL),
    reason="wealth-gate DB test runs only against a local/CI test DB, never prod",
)

CASES = {
    "concord": {2: (535_800, 129_621), 5: (495_033, 116_116),
                10: (464_411, 125_122), 15: (464_280, 128_575)},
    "darby": {2: (138_837, 59_417), 5: (155_904, 60_347),
              10: (155_982, 58_455), 15: (186_033, 64_618)},
    "standard": {2: (600_000, 130_000), 5: (550_000, 120_000),
                 10: (500_000, 110_000), 15: (480_000, 105_000)},
}


async def test_sql_tag_matches_python(db_session):
    jid = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO jurisdictions (id, name, state) VALUES (:id, :n, 'PA')"),
        {"id": jid, "n": f"WG {jid}"},
    )
    ids = {}
    for name, rings in CASES.items():
        row = await db_session.execute(
            text(
                "INSERT INTO parcels (jurisdiction_id, apn, in_flood_zone, in_wetland) "
                "VALUES (:jid, :apn, false, false) RETURNING id"
            ),
            {"jid": jid, "apn": name},
        )
        pid = row.scalar_one()
        ids[name] = pid
        for dt, (hv, hhi) in rings.items():
            await db_session.execute(
                text(
                    "INSERT INTO parcel_ring_metrics "
                    "(parcel_id, drive_time_minutes, median_home_value, median_hhi) "
                    "VALUES (:pid, :dt, :hv, :hhi)"
                ),
                {"pid": pid, "dt": dt, "hv": hv, "hhi": hhi},
            )
    await db_session.commit()
    try:
        for name, rings in CASES.items():
            got = (await db_session.execute(
                text(f"SELECT {wealth_tag_sql('p')} FROM parcels p WHERE p.id = :pid"),
                {"pid": ids[name]},
            )).scalar()
            assert got == gate_wealth(rings), (name, got)
    finally:
        await db_session.execute(
            text("DELETE FROM parcel_ring_metrics WHERE parcel_id = ANY(:ids)"),
            {"ids": list(ids.values())},
        )
        await db_session.execute(text("DELETE FROM parcels WHERE jurisdiction_id = :j"), {"j": jid})
        await db_session.execute(text("DELETE FROM jurisdictions WHERE id = :j"), {"j": jid})
        await db_session.commit()
