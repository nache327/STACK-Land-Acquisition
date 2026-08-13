"""The instant listing alert must respect the lead gate.

2026-08-13 Mercer: the first CoStar upload into a part-grounded county
emailed 16 "🔥 Hot deals · excellent" cards, of which 14 sat on parcels
with NO zoning verdict at all (Ewing/Hamilton/Lawrence/Robbinsville —
``lead_eligible=false``, ``gate_reason='low_confidence'``). The scorer
had correctly gated them; the alert worker filtered on ``score >= 85``
alone. The board (dashboard_push) and the daily digest (daily_email via
verdict_gate.lead_eligible_sql) both enforce the gate — the alert email
was the one consumer that skipped it, and an interrupt-style email is
the LAST place an unverified parcel should surface.

Structural pin, matching the repo convention for SQL-shaped guards
(see test_download_completeness.test_completeness_backstop_is_wired_*).
"""
from __future__ import annotations

import inspect


def test_alert_query_requires_lead_eligible():
    from app.workers import listing_alerts

    src = inspect.getsource(listing_alerts._alert_rows_for_filter)
    assert "pbs.lead_eligible = true" in src, (
        "listing alerts must enforce the same trust bar as the board and "
        "daily digest — score >= 85 alone lets ungrounded parcels email as "
        "'Hot deals'"
    )
    # The gate must sit in the live WHERE clause, not a comment: it has to
    # appear after the WHERE and before the final ORDER BY. (rsplit — the
    # zone_use_matrix LATERAL carries its own earlier ORDER BY.)
    where_to_order = src.split("WHERE l.jurisdiction_id", 1)[1].rsplit("ORDER BY", 1)[0]
    assert "pbs.lead_eligible = true" in where_to_order


def test_alert_score_floor_still_present():
    """The gate complements the score floor — both must hold."""
    from app.workers import listing_alerts

    src = inspect.getsource(listing_alerts._alert_rows_for_filter)
    assert "pbs.score >= :min_score" in src
    assert listing_alerts.ALERT_SCORE_MIN >= 85
