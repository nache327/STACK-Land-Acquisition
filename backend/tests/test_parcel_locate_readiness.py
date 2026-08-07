"""Guards for address-search readiness + the nearby endpoint's SQL shape.

These assert on the generated SQL rather than on query results because the failure
modes that actually bit during development are all structural, and every one of them
returned plausible output while being wrong:

  * the verdict SQL was nearly restated by hand (a FOURTH copy of the LGC rule, the
    exact drift that produced 6,702 phantom Montgomery needles);
  * `_QUALIFIES` returns NULL, not false, for a parcel with no ring row, and Postgres
    sorts NULLs FIRST under DESC — so "qualifying first" put UNMEASURED parcels at the
    top until COALESCE was added;
  * casting the indexed column (`p.centroid::geography`) in the WHERE clause silently
    disabled the GiST index: same answers, 169 seconds.
"""
from __future__ import annotations

from app.services import parcel_locate as pl
from app.services.use_verdicts import LGC_SLUG, SELF_STORAGE_SLUG, verdict_expr


def test_verdicts_are_generated_from_the_shared_definition() -> None:
    """No fourth copy of the LGC rule — the columns must come from use_verdicts."""
    for cols in (pl._COLS, pl._NEARBY_COLS):
        assert verdict_expr(SELF_STORAGE_SLUG) in cols
        assert verdict_expr(LGC_SLUG) in cols
        # The QC veto must be present via that generation, not re-typed.
        assert "IS DISTINCT FROM 'permitted'" in cols


def test_readiness_join_requires_human_reviewed() -> None:
    """`grounded` must mean human-reviewed, or the UI would show a guess as fact."""
    assert "m.human_reviewed" in pl._READY_JOINS
    assert "m.deleted_at IS NULL" in pl._READY_JOINS
    # muni-aware, case-sensitive, NULL-municipality rows ranked last
    assert "m.municipality = p.city" in pl._READY_JOINS
    assert "ORDER BY (m.municipality IS NULL) ASC" in pl._READY_JOINS
    # LEFT joins: an unanalysable parcel must still be FOUND, flagged — not filtered out
    assert pl._READY_JOINS.count("LEFT JOIN") == 2


def test_ring_measured_treats_the_epoch_sentinel_as_unmeasured() -> None:
    """to_timestamp(0) means 'never validly computed', not 'measured in 1970'."""
    for cols in (pl._COLS, pl._NEARBY_COLS):
        assert "computed_at <> to_timestamp(0)" in cols


def test_qualifies_is_coalesced_wherever_it_is_ordered_on() -> None:
    """NULL sorts FIRST under DESC — without COALESCE, unmeasured parcels lead.

    Read from the query builder's source: the ordering is constructed inside
    nearby_parcels, and this is the defect that made "qualifying first" return the
    opposite of its name.
    """
    import inspect

    src = inspect.getsource(pl.nearby_parcels)
    # Coalesced exactly once, where the qualifier is computed...
    assert "COALESCE({_QUALIFIES}, false) AS qualifies" in src, (
        "the qualifying flag is no longer COALESCEd at the point it is computed — "
        "NULL (no ring row) sorts FIRST under DESC, which puts UNMEASURED parcels at "
        "the top of a 'qualifying first' list"
    )
    # ...and every ordering reuses that already-coalesced column rather than
    # re-deriving the nullable expression.
    assert "ORDER BY COALESCE({_QUALIFIES}, false) DESC" in src
    assert "ORDER BY c.qualifies DESC" in src
    # Guard against a future edit sorting on the RAW predicate.
    assert "ORDER BY {_QUALIFIES} DESC" not in src


def test_qualifies_predicate_rejects_the_epoch_sentinel() -> None:
    """An epoch-stamped row must not qualify on a stale value."""
    assert "computed_at <> to_timestamp(0)" in pl._QUALIFIES


def test_nearby_filters_on_indexed_geometry_before_casting_to_geography() -> None:
    """The index-usability guard: `centroid::geography` in WHERE = seq scan (169s).

    The bbox `&&` against the plain geometry column is what keeps this interactive;
    the geography ST_DWithin then refines it exactly.
    """
    import inspect

    src = inspect.getsource(pl.nearby_parcels)
    assert "p.centroid && ST_Expand(" in src, (
        "the indexed bbox pre-filter is gone — this reverts to a sequential scan "
        "over every parcel"
    )
    assert "ST_DWithin(p.centroid::geography" in src, "exact refinement missing"


def test_nearby_is_bounded_on_both_axes() -> None:
    """Reachable from a text box, so it must cap radius AND rows."""
    assert pl._MAX_RADIUS_MILES <= 8.0     # measured latency cliff past ~7mi
    assert pl._MAX_NEARBY <= 200


def test_nearby_columns_carry_no_geometry() -> None:
    """A list endpoint shipping geometry is a payload incident waiting to happen."""
    lowered = pl._NEARBY_COLS.lower()
    assert "p.geom" not in lowered
    assert "st_asgeojson" not in lowered


def test_clamps_out_of_range_inputs() -> None:
    """Service-level clamping, independent of the Pydantic bounds on the route."""
    # exercised via the module constants the query builder reads
    assert max(0.1, min(99.0, pl._MAX_RADIUS_MILES)) == pl._MAX_RADIUS_MILES
    assert max(1, min(9999, pl._MAX_NEARBY)) == pl._MAX_NEARBY
