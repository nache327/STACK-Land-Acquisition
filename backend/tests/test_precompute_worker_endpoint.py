"""Worker-path precompute endpoint — confirms it enqueues to the Dramatiq worker
(not a web BackgroundTask). See discipline-catch #12: web BackgroundTask is the
wrong execution mode for >5min ingest jobs.
"""
import asyncio
import uuid

import pytest

import app.config
import app.services.job_queue as job_queue
from app.api.jurisdictions import precompute_ring_metrics_worker
from fastapi import HTTPException


class _FakeJur:
    name = "Test County, NJ"


class _FakeDB:
    def __init__(self, jur):
        self._jur = jur

    async def get(self, _model, _jid):
        return self._jur


def test_worker_endpoint_enqueues_to_worker(monkeypatch):
    # mapbox_enabled is a property over mapbox_token — set the token to make it True
    monkeypatch.setattr(app.config.settings, "mapbox_token", "test-token", raising=False)
    calls = []
    monkeypatch.setattr(
        job_queue, "enqueue_ring_metrics_precompute", lambda jid: calls.append(jid)
    )
    jid = uuid.uuid4()
    res = asyncio.run(precompute_ring_metrics_worker(jid, db=_FakeDB(_FakeJur())))

    assert calls == [jid], "endpoint must enqueue exactly once to the worker path"
    assert res["status"] == "enqueued"
    assert res["path"] == "worker"
    assert res["jurisdiction_id"] == str(jid)
    assert res["jurisdiction_name"] == "Test County, NJ"


def test_worker_endpoint_503_when_mapbox_unconfigured(monkeypatch):
    monkeypatch.setattr(app.config.settings, "mapbox_token", "", raising=False)
    monkeypatch.setattr(
        job_queue, "enqueue_ring_metrics_precompute",
        lambda jid: pytest.fail("must NOT enqueue when mapbox unconfigured"),
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(precompute_ring_metrics_worker(uuid.uuid4(), db=_FakeDB(_FakeJur())))
    assert ei.value.status_code == 503


def test_worker_endpoint_404_unknown_jurisdiction(monkeypatch):
    monkeypatch.setattr(app.config.settings, "mapbox_token", "test-token", raising=False)
    monkeypatch.setattr(
        job_queue, "enqueue_ring_metrics_precompute",
        lambda jid: pytest.fail("must NOT enqueue for unknown jurisdiction"),
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(precompute_ring_metrics_worker(uuid.uuid4(), db=_FakeDB(None)))
    assert ei.value.status_code == 404
