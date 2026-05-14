"""Redis-backed key/value store for long-running async job state.

Originally the ``_rematch-all`` and ``_score-all`` endpoints kept their
job dicts in a module-level Python dict. That works for a single
Railway dyno but breaks two ways:

  1. A deploy mid-job restarts the container and wipes the dict, so the
     status endpoint 404s even though the underlying work either
     finished (if the bg task got far enough) or is gone forever.
  2. If Railway ever scales to multiple instances, the POST + GET
     requests may hit different instances and not see each other's
     state.

Both failure modes are real (the deploy-wipe one hit us in production
during this session). This module moves the state to the project's
existing Redis instance — the same one Dramatiq's broker uses — so it
survives restarts and is shared across instances.

API is intentionally minimal: set, get, and a sliding TTL. Job IDs
auto-evict 24h after their last set, which is plenty for any sensible
poll cycle and bounds Redis usage.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as redis_async

from app.config import settings

logger = logging.getLogger(__name__)

# Shared async Redis client. Lazily created so importing this module
# doesn't connect during test collection or Alembic runs.
_client: redis_async.Redis | None = None


def _get_client() -> redis_async.Redis:
    global _client
    if _client is None:
        _client = redis_async.Redis.from_url(
            settings.redis_url, decode_responses=True
        )
    return _client


_KEY_PREFIX = "parcellogic:job_state:"
# 24h covers any sensible poll-and-forget pattern. Long-running jobs
# (e.g., 65-county _score-all) refresh the TTL each time progress is
# written, so they never expire mid-run.
_DEFAULT_TTL_SEC = 24 * 60 * 60


def _k(job_id: str) -> str:
    return f"{_KEY_PREFIX}{job_id}"


async def set_job_state(
    job_id: str, state: dict[str, Any], ttl_sec: int = _DEFAULT_TTL_SEC
) -> None:
    """Persist ``state`` for ``job_id`` with a 24h sliding TTL.

    Call this whenever the in-flight job updates a counter — each call
    refreshes the TTL so a long-running job doesn't get evicted mid-run.
    """
    client = _get_client()
    try:
        await client.set(_k(job_id), json.dumps(state, default=str), ex=ttl_sec)
    except Exception:
        # Don't let Redis hiccups break the work the bg task is doing.
        # The status endpoint will degrade to 404 but the underlying
        # job continues regardless.
        logger.exception("set_job_state failed for job=%s (continuing)", job_id)


async def get_job_state(job_id: str) -> dict[str, Any] | None:
    """Read job state, or None when the key is missing/expired."""
    client = _get_client()
    try:
        raw = await client.get(_k(job_id))
    except Exception:
        logger.exception("get_job_state failed for job=%s", job_id)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("job state for %s contained malformed JSON", job_id)
        return None
