"""LoopNet parser — stub. Drop a real export in backend/uploads/ and
fill in the column mapping (mirror app/services/listings_parsers/costar.py).

The fingerprint returns False so the dispatcher never auto-picks it
until parse logic is real. Users can still force it via source='loopnet'
in the upload request, but they'll get NotImplementedError.
"""
from __future__ import annotations


class Parser:
    name = "loopnet"

    @classmethod
    def fingerprint(cls, columns: list[str]) -> bool:
        return False

    @classmethod
    def parse_dataframe(cls, df, filename: str):
        raise NotImplementedError(
            "LoopNet parser not yet built. Drop a sample export at "
            "backend/uploads/<file>.xlsx and fill in the column mapping."
        )


__all__ = ["Parser"]
