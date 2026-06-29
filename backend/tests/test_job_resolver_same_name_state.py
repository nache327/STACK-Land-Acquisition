"""Regression test for catch #46 — the job resolver's same-name + different-state
collision (Montgomery County PA vs MD).

Before the fix, POST /api/jobs resolved an existing jurisdiction by stripping the
", XX" state suffix from BOTH the input and the stored name, then calling
scalar_one_or_none(). Once both "Montgomery County, PA" and "Montgomery County, MD"
were ingested, both rows stripped to "montgomery county" → the query returned 2
rows → MultipleResultsFound → 500.

The fix (resolve_existing_jurisdiction): a state-suffixed input matches the FULL
name exactly; a suffix-less input falls back to the stripped match and raises a
clear 409 when that is ambiguous.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.jobs import resolve_existing_jurisdiction
from app.models.jurisdiction import Jurisdiction


async def _seed(db, *names: str) -> None:
    # jurisdictions.state is NOT NULL; the resolver matches on `name` only, so a
    # placeholder state is fine for bare-name rows (legacy data stored the name
    # without the suffix but always carried a state column).
    for n in names:
        state = n.rsplit(",", 1)[1].strip() if "," in n else "XX"
        db.add(Jurisdiction(name=n, state=state))
    await db.flush()


@pytest.mark.asyncio(loop_scope="session")
async def test_state_suffix_disambiguates_montgomery(db_session) -> None:
    await _seed(db_session, "Montgomery County, PA", "Montgomery County, MD")

    pa = await resolve_existing_jurisdiction("Montgomery County, PA", db_session)
    md = await resolve_existing_jurisdiction("Montgomery County, MD", db_session)

    assert pa is not None and pa.name == "Montgomery County, PA"
    assert md is not None and md.name == "Montgomery County, MD"
    assert pa.id != md.id  # the bug returned 500 here instead of two distinct rows


@pytest.mark.asyncio(loop_scope="session")
async def test_suffixless_ambiguous_raises_409(db_session) -> None:
    await _seed(db_session, "Montgomery County, PA", "Montgomery County, MD")

    with pytest.raises(HTTPException) as exc:
        await resolve_existing_jurisdiction("Montgomery County", db_session)
    assert exc.value.status_code == 409
    assert "PA" in exc.value.detail and "MD" in exc.value.detail


@pytest.mark.asyncio(loop_scope="session")
async def test_suffixless_unambiguous_still_resolves(db_session) -> None:
    """A bare name with only ONE ingested state must still resolve (legacy path)."""
    await _seed(db_session, "Salt Lake County, UT")

    got = await resolve_existing_jurisdiction("Salt Lake County", db_session)
    assert got is not None and got.name == "Salt Lake County, UT"


@pytest.mark.asyncio(loop_scope="session")
async def test_suffix_input_matches_legacy_bare_stored_name(db_session) -> None:
    """Old rows stored WITHOUT a suffix must still resolve from a suffixed input
    when the match is unambiguous."""
    await _seed(db_session, "Draper City")  # stored bare, no state

    got = await resolve_existing_jurisdiction("Draper City, UT", db_session)
    assert got is not None and got.name == "Draper City"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_match_returns_none(db_session) -> None:
    await _seed(db_session, "Montgomery County, PA")

    assert await resolve_existing_jurisdiction("Bucks County, PA", db_session) is None


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("family", ["Franklin County", "Washington County", "Lincoln County"])
async def test_same_name_family_future_proofed(db_session, family) -> None:
    """The Franklin/Washington/Lincoln/Madison/Jefferson family will collide the
    same way once two states are ingested — the full-name match must hold."""
    await _seed(db_session, f"{family}, PA", f"{family}, OH")

    pa = await resolve_existing_jurisdiction(f"{family}, PA", db_session)
    oh = await resolve_existing_jurisdiction(f"{family}, OH", db_session)
    assert pa is not None and pa.name == f"{family}, PA"
    assert oh is not None and oh.name == f"{family}, OH"
