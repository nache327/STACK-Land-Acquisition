"""Worker-path listing-match endpoint — confirms it enqueues to the Dramatiq
worker (not a web BackgroundTask). See discipline-catch #25: the web
BackgroundTask matcher silently stalled on the Montgomery MD ingest (224
listings, 0 matched under dyno contention). Same family as #12 (precompute).
"""
import asyncio
import uuid

import pytest

import app.services.job_queue as job_queue
from app.api.jurisdictions import match_listings_worker
from fastapi import HTTPException


class _FakeJur:
    name = "Test County, MD"


class _FakeDB:
    def __init__(self, jur):
        self._jur = jur

    async def get(self, _model, _jid):
        return self._jur


def test_match_worker_endpoint_enqueues_to_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(
        job_queue, "enqueue_listing_match",
        lambda jid, source="costar": calls.append((jid, source)),
    )
    jid = uuid.uuid4()
    res = asyncio.run(match_listings_worker(jid, source="costar", db=_FakeDB(_FakeJur())))

    assert calls == [(jid, "costar")], "endpoint must enqueue exactly once to the worker path"
    assert res["status"] == "enqueued"
    assert res["path"] == "worker"
    assert res["jurisdiction_id"] == str(jid)
    assert res["source"] == "costar"


def test_match_worker_endpoint_404_unknown_jurisdiction(monkeypatch):
    monkeypatch.setattr(
        job_queue, "enqueue_listing_match",
        lambda jid, source="costar": pytest.fail("must NOT enqueue for unknown jurisdiction"),
    )
    with pytest.raises(HTTPException) as ei:
        asyncio.run(match_listings_worker(uuid.uuid4(), source="costar", db=_FakeDB(None)))
    assert ei.value.status_code == 404


def test_match_worker_actor_does_not_use_background_task():
    """The worker path must be a Dramatiq actor, not a FastAPI BackgroundTask.
    Guards the regression: enqueue_listing_match must dispatch via the actor's
    .send() (worker queue), and process_listing_match must be a dramatiq actor."""
    import dramatiq
    assert isinstance(job_queue.process_listing_match, dramatiq.Actor), \
        "process_listing_match must be a @dramatiq.actor (worker), not a web BackgroundTask"
    # enqueue_listing_match must dispatch to the worker via .send(), not run inline
    sent = []
    orig = job_queue.process_listing_match.send
    try:
        job_queue.process_listing_match.send = lambda *a, **k: sent.append((a, k))
        job_queue.enqueue_listing_match(uuid.uuid4(), "costar")
    finally:
        job_queue.process_listing_match.send = orig
    assert len(sent) == 1, "enqueue_listing_match must call actor.send() exactly once (worker dispatch)"
