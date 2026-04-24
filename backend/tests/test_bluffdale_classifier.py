"""
Regression tests for classify_bluffdale() in fix_partial_city_matrix.py.

These serve as golden fixtures: if any of these fail after a code change,
a storage classification regression has been introduced.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fix_partial_city_matrix import classify_bluffdale


# ── Must-be-prohibited zones ──────────────────────────────────────────────────

def test_mixed_use_is_prohibited():
    cls = classify_bluffdale("Mixed Use")
    assert cls.self_storage == "prohibited"
    assert cls.mini_warehouse == "prohibited"
    assert cls.luxury_garage_condo == "prohibited"


def test_rmf_multifamily_is_prohibited():
    cls = classify_bluffdale("R-MF Multifamily")
    assert cls.self_storage == "prohibited"
    assert cls.mini_warehouse == "prohibited"


def test_r143_is_prohibited():
    cls = classify_bluffdale("R-1-43")
    assert cls.self_storage == "prohibited"


def test_undesignated_is_prohibited():
    cls = classify_bluffdale("Undesignated")
    assert cls.self_storage == "prohibited"


def test_civic_is_prohibited():
    cls = classify_bluffdale("CI Civic Institutional")
    assert cls.self_storage == "prohibited"


# ── Must-be-permitted zones ───────────────────────────────────────────────────

def test_i1_light_industrial_is_permitted():
    cls = classify_bluffdale("I-1 Light Industry")
    assert cls.self_storage == "permitted"
    assert cls.mini_warehouse == "permitted"
    assert cls.light_industrial == "permitted"


def test_commercial_storage_is_permitted():
    cls = classify_bluffdale("SG-1 Commercial Storage")
    assert cls.self_storage == "permitted"


def test_heavy_commercial_is_permitted():
    cls = classify_bluffdale("Heavy Commercial")
    assert cls.self_storage == "permitted"


# ── Must-be-conditional zones ─────────────────────────────────────────────────

def test_gc1_is_conditional():
    cls = classify_bluffdale("GC-1")
    assert cls.self_storage == "conditional"


def test_a5_agricultural_is_conditional():
    cls = classify_bluffdale("A-5 Agricultural")
    assert cls.self_storage == "conditional"


def test_sd_special_district_is_conditional():
    cls = classify_bluffdale("SD-X Special District")
    assert cls.self_storage == "conditional"


# ── Unknown zone codes use conservative prohibited default ────────────────────

def test_unknown_zone_is_prohibited():
    cls = classify_bluffdale("UNKNOWN_XYZ_ZONE")
    assert cls.self_storage == "prohibited"
    assert cls.confidence <= 0.5
