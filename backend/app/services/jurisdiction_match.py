"""Jurisdiction-name normalization for the create-job lookup.

Lives in its own module (no fastapi / sqlalchemy imports) so the unit test
can exercise it directly without dragging in the rest of the FastAPI app.
"""
from __future__ import annotations


def strip_state_suffix_lower(name: str) -> str:
    """Normalize a free-text jurisdiction input for case-insensitive matching:
    lowercase + drop a trailing ", XX" two-letter state code.

    So "Salt Lake County, UT", "salt lake county, ut", and bare "Salt Lake
    County" all collapse to "salt lake county" for comparison. The two-
    letter heuristic intentionally doesn't strip ", Borough" or
    ", Township" because those are part of the place name in some
    jurisdictions, not a state code.
    """
    s = name.strip()
    if "," in s:
        head, tail = s.rsplit(",", 1)
        tail = tail.strip()
        if len(tail) == 2 and tail.isalpha():
            s = head.strip()
    return s.lower()
