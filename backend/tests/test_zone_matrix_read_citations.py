"""Regression: GET /jurisdictions/{id}/zones must not 500 on stored citations
that exceed the parser's write-time 200-char quote cap.

Bergen County's matrix rows were parsed from real ordinance PDFs and carry
quotes longer than 200 chars. The read schema previously reused the
write-time CitationSchema (quote: max_length=200), so serializing those rows
raised ResponseValidationError -> HTTP 500, making the whole county's zone
matrix (and the verifier) unloadable. The read path now uses a tolerant
CitationRead; the write contract keeps the 200-char guard.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.zone_use_matrix import (
    CitationRead,
    CitationSchema,
    ZoneUseMatrixRead,
)


def _row(citations: list[dict] | None) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    return dict(
        id=1,
        jurisdiction_id=uuid.uuid4(),
        zone_code="C-2",
        zone_name=None,
        municipality="Paramus borough",
        self_storage="permitted",
        mini_warehouse="permitted",
        light_industrial="conditional",
        luxury_garage_condo="unclear",
        citations=citations,
        confidence=0.7,
        human_reviewed=False,
        notes=None,
        classification_source="llm",
        created_at=now,
        updated_at=now,
    )


def test_write_contract_still_caps_quote_length() -> None:
    # The parser/write path must keep quotes short.
    with pytest.raises(ValidationError):
        CitationSchema(section="§1", quote="x" * 201)


def test_read_tolerates_overlong_stored_quote() -> None:
    # The Bergen bug: a 350-char stored quote must read cleanly, not 500.
    m = ZoneUseMatrixRead.model_validate(_row([{"section": "§40-5", "quote": "x" * 350}]))
    assert m.citations is not None
    assert len(m.citations[0].quote) == 350


def test_read_tolerates_partial_citation() -> None:
    # A stored citation missing section or quote degrades, doesn't raise.
    m = ZoneUseMatrixRead.model_validate(_row([{"section": "§9"}, {"quote": "q only"}]))
    assert [(c.section, c.quote) for c in m.citations] == [("§9", None), (None, "q only")]


def test_read_tolerates_null_citations() -> None:
    m = ZoneUseMatrixRead.model_validate(_row(None))
    assert m.citations is None


def test_citation_read_fields_optional() -> None:
    assert CitationRead().section is None
    assert CitationRead(quote="q").quote == "q"
