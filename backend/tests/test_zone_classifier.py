"""
Unit tests for the universal zone character classifier and shared utilities.
"""
import pytest
from app.services.zone_classifier import (
    PerUseClassification,
    apply_luxury_garage_inference,
    classify_by_zone_character,
    storage_cls,
)


# ── PerUseClassification + storage_cls ────────────────────────────────────────

def test_storage_cls_sets_all_storage_uses():
    cls = storage_cls("permitted", 0.80, "test")
    assert cls.self_storage == "permitted"
    assert cls.mini_warehouse == "permitted"
    assert cls.light_industrial == "permitted"


def test_storage_cls_explicit_light_industrial():
    cls = storage_cls("conditional", 0.70, "test", light_industrial="permitted")
    assert cls.self_storage == "conditional"
    assert cls.mini_warehouse == "conditional"
    assert cls.light_industrial == "permitted"


def test_storage_cls_infers_luxury_garage_from_storage():
    cls = storage_cls("conditional", 0.70, "test")
    assert cls.luxury_garage_condo == "conditional"


def test_storage_cls_prohibited_luxury_garage_when_prohibited():
    cls = storage_cls("prohibited", 0.80, "test")
    assert cls.luxury_garage_condo == "prohibited"


# ── apply_luxury_garage_inference ─────────────────────────────────────────────

def test_inference_permitted_storage_yields_permitted_lgc():
    cls = PerUseClassification(
        self_storage="permitted", mini_warehouse="conditional",
        light_industrial="prohibited", luxury_garage_condo="unclear",
        confidence=0.7, notes="test",
    )
    result = apply_luxury_garage_inference(cls)
    assert result.luxury_garage_condo == "permitted"


def test_inference_conditional_mw_yields_conditional_lgc():
    cls = PerUseClassification(
        self_storage="prohibited", mini_warehouse="conditional",
        light_industrial="prohibited", luxury_garage_condo="unclear",
        confidence=0.7, notes="test",
    )
    result = apply_luxury_garage_inference(cls)
    assert result.luxury_garage_condo == "conditional"


def test_inference_li_conditional_yields_conditional_lgc():
    cls = PerUseClassification(
        self_storage="prohibited", mini_warehouse="prohibited",
        light_industrial="conditional", luxury_garage_condo="unclear",
        confidence=0.7, notes="test",
    )
    result = apply_luxury_garage_inference(cls)
    assert result.luxury_garage_condo == "conditional"


def test_inference_all_prohibited_yields_prohibited_lgc():
    cls = PerUseClassification(
        self_storage="prohibited", mini_warehouse="prohibited",
        light_industrial="prohibited", luxury_garage_condo="unclear",
        confidence=0.7, notes="test",
    )
    result = apply_luxury_garage_inference(cls)
    assert result.luxury_garage_condo == "prohibited"


def test_inference_skips_non_unclear():
    cls = PerUseClassification(
        self_storage="permitted", mini_warehouse="permitted",
        light_industrial="permitted", luxury_garage_condo="prohibited",
        confidence=0.7, notes="test",
    )
    result = apply_luxury_garage_inference(cls)
    assert result.luxury_garage_condo == "prohibited"


# ── classify_by_zone_character — industrial → permitted ───────────────────────

@pytest.mark.parametrize("code", ["I-1", "I-2", "M-1", "M-2", "LI", "LM", "BP",
                                   "I 1", "M1", "M2", "HI", "HM",
                                   "Light Industrial", "Heavy Industrial",
                                   "Business Park"])
def test_industrial_is_permitted(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "permitted", f"Expected permitted for {code!r}"
    assert cls.mini_warehouse == "permitted"
    assert cls.light_industrial == "permitted"


# ── classify_by_zone_character — commercial → conditional ─────────────────────

@pytest.mark.parametrize("code", ["C-1", "C-2", "C-3", "C-G", "B-1", "GC", "HC",
                                   "NC", "SC", "CC", "TC",
                                   "General Commercial", "Highway Commercial",
                                   "Neighborhood Commercial"])
def test_commercial_is_conditional(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "conditional", f"Expected conditional for {code!r}"
    assert cls.mini_warehouse == "conditional"


# ── classify_by_zone_character — residential MU → prohibited ──────────────────

@pytest.mark.parametrize("code", ["MU", "RMU", "MXD", "Mixed Use",
                                   "Mixed-Use", "Residential/Commercial"])
def test_residential_mu_is_prohibited(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "prohibited", f"Expected prohibited for {code!r}"


# ── classify_by_zone_character — commercial MU → conditional ──────────────────

@pytest.mark.parametrize("code", ["MU-C", "MXD-C", "TOD", "CX"])
def test_commercial_mu_is_conditional(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "conditional", f"Expected conditional for {code!r}"


# ── classify_by_zone_character — residential → prohibited ─────────────────────

@pytest.mark.parametrize("code", ["R-1", "R-1-8", "R-2", "R-3", "RA-1",
                                   "R-MF", "RMF", "SF", "MH",
                                   "Single-Family", "Multifamily", "Residential",
                                   "Apartment"])
def test_residential_is_prohibited(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "prohibited", f"Expected prohibited for {code!r}"
    assert cls.light_industrial == "prohibited"


# ── classify_by_zone_character — agricultural → prohibited ───────────────────

@pytest.mark.parametrize("code", ["A-1", "A-5", "AG", "FA"])
def test_agricultural_is_prohibited(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "prohibited", f"Expected prohibited for {code!r}"


# ── classify_by_zone_character — civic/open space → prohibited ───────────────

@pytest.mark.parametrize("code", ["OS", "POS", "PL", "PI", "Open Space",
                                   "Civic", "Institutional", "Public Facility"])
def test_civic_is_prohibited(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "prohibited", f"Expected prohibited for {code!r}"


# ── classify_by_zone_character — unknown → prohibited (conservative) ─────────

@pytest.mark.parametrize("code", ["XYZPDQ", "UNKNOWN_ZONE", "???", ""])
def test_unknown_is_prohibited(code):
    cls = classify_by_zone_character(code)
    assert cls.self_storage == "prohibited", f"Expected prohibited for unknown {code!r}"
    assert cls.confidence <= 0.5


# ── Per-use granularity ───────────────────────────────────────────────────────

def test_commercial_light_industrial_is_conditional():
    cls = classify_by_zone_character("C-1")
    assert cls.light_industrial == "conditional"


def test_residential_light_industrial_is_prohibited():
    cls = classify_by_zone_character("R-1")
    assert cls.light_industrial == "prohibited"


def test_industrial_light_industrial_is_permitted():
    cls = classify_by_zone_character("I-1")
    assert cls.light_industrial == "permitted"
