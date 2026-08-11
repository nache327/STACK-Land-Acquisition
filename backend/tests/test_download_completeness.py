"""Guards against silently-truncated ArcGIS downloads.

Mercer County NJ ingested exactly 100,000 of 127,186 parcels (2026-08-11): an AGOL
node returned a truncated ``returnIdsOnly`` list — deterministically from the prod
worker while the full list came back elsewhere, with no ``exceededTransferLimit``
flag. The old code trusted whatever list arrived AND then adopted its length as the
authoritative total, so the county looked complete while missing 21% of its parcels.
A needle among the missing 27k simply would not exist — the silent-confident-wrong
class, one layer down from the ring trust trap.

Two independent guards, tested separately:
  1. ``_get_all_object_ids`` pages past a truncated id list using
     ``OBJECTID > max(seen)`` until it reaches the expected count or stops growing.
  2. ``download_all_features`` re-counts after assembly and REFUSES a >5% shortfall.
"""
from __future__ import annotations

import pytest

from app.services import arcgis_query as aq


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def _ids_server(pages: list[list[int]]):
    """Simulates an AGOL node that truncates returnIdsOnly.

    First call returns pages[0]; each subsequent call must carry an
    ``OBJECTID > <max>`` refinement and gets the next page. Records the WHERE
    clauses so the test can assert the paging actually used disjoint ranges.
    """
    calls: list[str] = []

    async def fake_send(client, method, url, *, params=None, data=None, timeout=0):
        where = (params or {}).get("where", "")
        calls.append(where)
        idx = min(len(calls) - 1, len(pages) - 1)
        page = pages[idx] if idx < len(pages) else []
        # honour the OBJECTID > N refinement like a real server would
        if "OBJECTID >" in where:
            floor = int(where.rsplit(">", 1)[1].strip().rstrip(")"))
            page = [i for i in page if i > floor]
        return _FakeResponse({"objectIds": page})

    return fake_send, calls


@pytest.mark.asyncio
async def test_truncated_id_list_is_paged_to_completion(monkeypatch) -> None:
    """The Mercer shape: server hands back a truncated list; expected_count says
    it is short; the pager keeps going until it has everything."""
    full = list(range(1, 251))
    fake_send, calls = _ids_server([full[:100], full[100:200], full[200:]])
    monkeypatch.setattr(aq, "_send_with_retry", fake_send)

    got = await aq._get_all_object_ids("http://x/FeatureServer/0", "C='M'",
                                       client=None, expected_count=250)
    assert got == full, f"expected all 250 ids, got {len(got or [])}"
    assert len(calls) >= 3
    assert all("OBJECTID >" in w for w in calls[1:]), (
        "follow-up pages must use disjoint OBJECTID ranges, not re-fetch"
    )


@pytest.mark.asyncio
async def test_id_paging_terminates_when_server_stops_growing(monkeypatch) -> None:
    """A server that keeps returning the same short list must not loop forever —
    and the caller still gets what exists rather than nothing."""
    short = list(range(1, 101))
    fake_send, calls = _ids_server([short, []])
    monkeypatch.setattr(aq, "_send_with_retry", fake_send)

    got = await aq._get_all_object_ids("http://x/FeatureServer/0", "C='M'",
                                       client=None, expected_count=250)
    assert got == short
    assert len(calls) == 2          # first fetch + one empty follow-up, then stop


@pytest.mark.asyncio
async def test_no_expected_count_preserves_old_single_fetch(monkeypatch) -> None:
    """Without an expected count there is nothing to reconcile against — one
    fetch, no paging, exactly the pre-fix behavior."""
    fake_send, calls = _ids_server([[3, 1, 2]])
    monkeypatch.setattr(aq, "_send_with_retry", fake_send)

    got = await aq._get_all_object_ids("http://x/FeatureServer/0", "1=1", client=None)
    assert got == [1, 2, 3]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unsupported_returnidsonly_still_returns_none(monkeypatch) -> None:
    async def boom(client, method, url, *, params=None, data=None, timeout=0):
        raise RuntimeError("returnIdsOnly unsupported")
    monkeypatch.setattr(aq, "_send_with_retry", boom)

    got = await aq._get_all_object_ids("http://x/FeatureServer/0", "1=1",
                                       client=None, expected_count=100)
    assert got is None              # caller falls back to offset pagination


def test_completeness_backstop_is_wired_fail_closed() -> None:
    """Structural: the recount must abort on a >5% shortfall, use a FRESH client
    (the pooled one is closed by that point — passing it would make the check
    silently vacuous), and only the recount ERROR path fails open."""
    import inspect

    src = inspect.getsource(aq.download_all_features)
    assert "INCOMPLETE DOWNLOAD" in src
    assert "0.95" in src
    assert "client=None" in src.split("INCOMPLETE DOWNLOAD")[0].rsplit("try:", 1)[1], (
        "the recount must not reuse the closed pooled client"
    )
    assert "raise ValueError" in src


@pytest.mark.asyncio
async def test_holey_id_list_falls_back_to_offset_pagination(monkeypatch) -> None:
    """The Mercer shape, round 2: the server's id list is missing ids MID-RANGE
    (holes), so '> max' paging recovers almost nothing. An unrepairable short
    list must be DISCARDED in favor of offset pagination — a hole-y subset that
    gets trusted downloads 79% of a county and calls it done."""
    # ids 1..100 with 40..60 missing; expected 120. Follow-up (>100) finds nothing.
    holey = [i for i in range(1, 101) if not (40 <= i <= 60)]

    async def fake_send(client, method, url, *, params=None, data=None, timeout=0):
        where = (params or {}).get("where", "")
        if "OBJECTID >" in where:
            return _FakeResponse({"objectIds": []})
        return _FakeResponse({"objectIds": holey})

    monkeypatch.setattr(aq, "_send_with_retry", fake_send)
    got = await aq._get_all_object_ids("http://x/FeatureServer/0", "1=1",
                                       client=None, expected_count=120)
    # the helper returns what it could get...
    assert got is not None and len(got) == len(holey)
    # ...and download_all_features must then refuse to use it (structural pin):
    import inspect
    src = inspect.getsource(aq.download_all_features)
    assert "len(oids) < total * 0.99" in src
    assert "oids = None" in src, "short unrepairable id lists must fall back to offsets"
