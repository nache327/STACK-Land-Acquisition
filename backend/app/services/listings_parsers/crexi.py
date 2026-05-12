"""Crexi parser — stub. See loopnet.py for the same pattern."""
from __future__ import annotations


class Parser:
    name = "crexi"

    @classmethod
    def fingerprint(cls, columns: list[str]) -> bool:
        return False

    @classmethod
    def parse_dataframe(cls, df, filename: str):
        raise NotImplementedError(
            "Crexi parser not yet built. Drop a sample export at "
            "backend/uploads/<file>.xlsx and fill in the column mapping."
        )


__all__ = ["Parser"]
