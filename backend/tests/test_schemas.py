"""Unit tests for Pydantic schemas — no database required."""
import pytest
from pydantic import ValidationError

from app.schemas.job import JobCreate
from app.schemas.parcel import ParcelFilter
from app.schemas.zone_use_matrix import ParserOutput


def test_job_create_defaults_to_all_uses() -> None:
    job = JobCreate(jurisdiction="Draper, UT")
    assert set(job.target_uses) == {
        "self_storage",
        "mini_warehouse",
        "light_industrial",
        "luxury_garage_condo",
    }


def test_job_create_rejects_empty_jurisdiction() -> None:
    with pytest.raises(ValidationError):
        JobCreate(jurisdiction="")


def test_parcel_filter_defaults() -> None:
    f = ParcelFilter()
    # Filter toggles default to False (opt-in): schema has vacant_only=False
    # and exclude_flood=False. The original assertion in the initial commit
    # was wrong and never reflected the actual schema behavior.
    assert f.vacant_only is False
    assert f.exclude_flood is False
    assert f.exclude_wetland is False
    assert f.page == 1
    assert f.page_size == 50


def test_parser_output_valid() -> None:
    raw = {
        "zones": [
            {
                "code": "M1",
                "name": "Light Industrial",
                "self_storage": "permitted",
                "mini_warehouse": "permitted",
                "light_industrial": "permitted",
                "luxury_garage_condo": "permitted",
                "citations": [{"section": "9-13-040", "quote": "Self-storage warehouses"}],
                "confidence": 0.95,
                "notes": None,
            }
        ],
        "unknown_zones": [],
        "parser_warnings": [],
    }
    output = ParserOutput.model_validate(raw)
    assert output.zones[0].code == "M1"
    assert output.zones[0].self_storage.value == "permitted"


def test_parser_output_rejects_invalid_permission() -> None:
    raw = {
        "zones": [
            {
                "code": "R1",
                "name": "Residential",
                "self_storage": "INVALID_VALUE",
                "mini_warehouse": "prohibited",
                "light_industrial": "prohibited",
                "luxury_garage_condo": "prohibited",
                "citations": [],
                "confidence": 0.99,
                "notes": None,
            }
        ],
        "unknown_zones": [],
        "parser_warnings": [],
    }
    with pytest.raises(ValidationError):
        ParserOutput.model_validate(raw)
