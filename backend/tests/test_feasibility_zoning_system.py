from types import SimpleNamespace
import uuid

import pytest

from app.models.parcel import Parcel
from app.services import feasibility


class FakeSession:
    def __init__(self, parcel: Parcel):
        self.parcel = parcel
        self.flushed = False

    async def get(self, model, key):
        return self.parcel if model is Parcel and key == self.parcel.id else None

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_feasibility_waits_for_owned_zoning_then_completes(monkeypatch):
    parcel = Parcel(id=123, jurisdiction_id=uuid.UUID("00000000-0000-0000-0000-000000000001"), apn="A-1")
    db = FakeSession(parcel)
    started_steps = []

    async def fake_start_job_step(db, job, step, metadata=None):
        record = SimpleNamespace(status="running", step=step, step_metadata=metadata or {})
        started_steps.append(record)
        return record

    async def missing_zoning(parcel_id, db):
        return None

    monkeypatch.setattr(feasibility, "start_job_step", fake_start_job_step)
    monkeypatch.setattr(feasibility, "get_zoning_from_db", missing_zoning)

    pending = await feasibility.run_parcel_feasibility(123, db)

    assert pending == {
        "status": "pending_zoning",
        "message": "Zoning data is being ingested",
    }
    assert started_steps[0].step == "zoning"
    assert started_steps[0].status == "waiting_for_data"

    rule = SimpleNamespace(
        city="Draper",
        zone_code="M1",
        density=None,
        max_units=None,
        min_lot_size=None,
        setbacks=None,
        height_limit=45.0,
        source="parcel_ingest",
        confidence=0.75,
    )

    async def found_zoning(parcel_id, db):
        return {"rule": rule, "overlay": SimpleNamespace(), "cache": SimpleNamespace()}

    monkeypatch.setattr(feasibility, "get_zoning_from_db", found_zoning)
    complete = await feasibility.run_parcel_feasibility(123, db)

    assert complete["status"] == "complete"
    assert complete["zoning"]["zone_code"] == "M1"
