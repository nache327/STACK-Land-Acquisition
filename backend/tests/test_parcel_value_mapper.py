"""Unit tests for app.services.parcel_value_mapper.

The mapper is the single place we extract assessed_value + is_residential
from per-state assessor source rows. These tests pin down what each state
mapper accepts so regressions surface immediately.
"""
from __future__ import annotations

import pytest

from app.services.parcel_value_mapper import map_value_and_residential


# ─── NJ MOD-IV ─────────────────────────────────────────────────────────

def test_nj_residential_house_with_net_value():
    raw = {"NET_VALUE": "475000", "PROP_CLASS": "2", "PAMS_PIN": "1330_42_3"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(475_000)
    assert is_res is True


def test_nj_commercial_property_not_residential():
    raw = {"NET_VALUE": "1200000", "PROP_CLASS": "4A"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(1_200_000)
    assert is_res is False


def test_nj_fallback_land_plus_improvement_when_no_net_value():
    raw = {"LAND_VAL": "300000", "IMPRVT_VAL": "175000", "PROP_CLASS": "2"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(475_000)
    assert is_res is True


def test_nj_case_insensitive_field_lookup():
    raw = {"net_value": 525000, "prop_class": "2"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(525_000)
    assert is_res is True


def test_nj_missing_class_yields_none_residential():
    raw = {"NET_VALUE": "475000"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(475_000)
    assert is_res is None


# ─── UT UGRC ───────────────────────────────────────────────────────────

def test_ut_residential_with_total_mkt_value():
    raw = {"TOTAL_MKT_VALUE": "650000", "PROP_CLASS": "Residential"}
    val, is_res = map_value_and_residential("UT", raw)
    assert val == pytest.approx(650_000)
    assert is_res is True


def test_ut_short_residential_code():
    raw = {"TOTAL_MKT_VALUE": "725000", "PROP_CLASS": "R"}
    val, is_res = map_value_and_residential("UT", raw)
    assert val == pytest.approx(725_000)
    assert is_res is True


def test_ut_landuse_fallback_for_residential():
    # Some UGRC counties only publish LAND_USE_CD. 1xx = residential.
    raw = {"TOTAL_VAL": "800000", "LAND_USE_CD": "110"}
    val, is_res = map_value_and_residential("UT", raw)
    assert val == pytest.approx(800_000)
    assert is_res is True


def test_ut_commercial_landuse_not_residential():
    raw = {"TOTAL_MKT_VALUE": "1500000", "LAND_USE_CD": "510"}
    val, is_res = map_value_and_residential("UT", raw)
    assert val == pytest.approx(1_500_000)
    assert is_res is False


# ─── PA Philadelphia OPA ───────────────────────────────────────────────

def test_pa_residential_market_value():
    raw = {"market_value": "450000", "category_code": "1"}
    val, is_res = map_value_and_residential("PA", raw)
    assert val == pytest.approx(450_000)
    assert is_res is True


def test_pa_commercial_not_residential():
    raw = {"market_value": "2500000", "category_code": "3"}
    val, is_res = map_value_and_residential("PA", raw)
    assert val == pytest.approx(2_500_000)
    assert is_res is False


# ─── FL DOR ────────────────────────────────────────────────────────────

def test_fl_single_family_residential():
    raw = {"JV": "850000", "DOR_UC": "0100"}
    val, is_res = map_value_and_residential("FL", raw)
    assert val == pytest.approx(850_000)
    assert is_res is True


def test_fl_condo_residential():
    raw = {"JV": "550000", "DOR_UC": "0400"}
    val, is_res = map_value_and_residential("FL", raw)
    assert is_res is True


def test_fl_industrial_not_residential():
    raw = {"JV": "3500000", "DOR_UC": "4100"}
    val, is_res = map_value_and_residential("FL", raw)
    assert val == pytest.approx(3_500_000)
    assert is_res is False


# ─── Edge cases ────────────────────────────────────────────────────────

def test_unknown_state_returns_none():
    raw = {"NET_VALUE": "500000", "PROP_CLASS": "2"}
    assert map_value_and_residential("ZZ", raw) == (None, None)


def test_empty_raw_returns_none():
    assert map_value_and_residential("NJ", {}) == (None, None)


def test_none_state_returns_none():
    assert map_value_and_residential(None, {"NET_VALUE": "500000"}) == (None, None)


def test_value_with_commas_parses():
    raw = {"NET_VALUE": "1,250,000", "PROP_CLASS": "2"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val == pytest.approx(1_250_000)
    assert is_res is True


def test_zero_value_treated_as_none():
    raw = {"NET_VALUE": "0", "PROP_CLASS": "2"}
    val, is_res = map_value_and_residential("NJ", raw)
    assert val is None
    assert is_res is True


def test_malformed_row_returns_none_no_exception():
    # The mapper should never raise on a malformed row — that would break
    # the whole ingest batch.
    raw = {"NET_VALUE": object()}  # str(object()) -> garbage
    val, _ = map_value_and_residential("NJ", raw)
    assert val is None
