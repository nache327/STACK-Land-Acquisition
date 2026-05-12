"""Source-agnostic listing parser registry.

Each provider (CoStar / LoopNet / Crexi / ...) ships its export
columns in a different layout. The parsers in this package normalize
those layouts to the canonical ``ListingRow`` dataclass in
``_common.py``, which mirrors the ``forsale_listings`` table columns.

Public entry point: ``parse_file(file_bytes, filename, source)``. If
``source`` is None, the dispatcher sniffs based on column fingerprints
in priority order: costar -> loopnet -> crexi -> generic fallback.
The "generic" parser expects canonical column names verbatim.

To add a new provider:
 1. Drop a sample export in ``backend/uploads/``
 2. Add ``yourprovider.py`` with a ``Parser`` class exposing
    ``fingerprint(columns)``, ``parse(file_bytes, filename)``
 3. Register it in ``_PARSERS`` below
"""
from __future__ import annotations

from io import BytesIO
from typing import Iterable

from app.services.listings_parsers._common import (
    ListingRow,
    ParseResult,
    ParserError,
    load_dataframe,
)
from app.services.listings_parsers import costar, crexi, generic, loopnet


# Priority order — first match wins. Generic is the fallback.
_PARSERS: list = [
    costar.Parser,
    loopnet.Parser,
    crexi.Parser,
    generic.Parser,
]

_SOURCE_KEY_TO_PARSER = {
    "costar":  costar.Parser,
    "loopnet": loopnet.Parser,
    "crexi":   crexi.Parser,
    "generic": generic.Parser,
    "manual":  generic.Parser,
}


def parse_file(
    file_bytes: bytes,
    filename: str,
    source: str | None = None,
) -> ParseResult:
    """Parse an uploaded listings export.

    If ``source`` is given, the matching parser is used unconditionally.
    Otherwise the dispatcher sniffs the column header against each
    provider's fingerprint and falls back to ``generic`` if none match.

    Raises ``ParserError`` if the file can't be opened or no parser
    accepts the columns.
    """
    df = load_dataframe(file_bytes, filename)
    columns = [str(c).strip() for c in df.columns]

    if source:
        cls = _SOURCE_KEY_TO_PARSER.get(source.lower())
        if cls is None:
            raise ParserError(f"Unknown source '{source}'. Known: {list(_SOURCE_KEY_TO_PARSER)}")
        return cls.parse_dataframe(df, filename=filename)

    # Sniff
    for cls in _PARSERS:
        try:
            if cls.fingerprint(columns):
                return cls.parse_dataframe(df, filename=filename)
        except NotImplementedError:
            # Stub parsers (LoopNet/Crexi) until exports arrive. Skip
            # them during sniff — we'd never auto-pick a stub.
            continue
    raise ParserError(
        f"No parser matched the column header. Columns: {columns!r}"
    )


def known_sources() -> Iterable[str]:
    return tuple(_SOURCE_KEY_TO_PARSER.keys())


__all__ = [
    "ListingRow",
    "ParseResult",
    "ParserError",
    "parse_file",
    "known_sources",
]
