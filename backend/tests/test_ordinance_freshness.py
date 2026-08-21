"""Unit tests for the ordinance freshness sentinel's pure helpers (no DB, no network).

Fixture snippets mirror real host output: the eCode360 markup is trimmed from a
live Dedham MA code page (client DE3083, server-rendered "New Laws (9)" badge),
and the Municode shape from a live Jobs/latest/10075 response (Scottsdale).
"""
from app.services.ordinance_freshness import (
    Fingerprint,
    decide_drift,
    detect_host_kind,
    extract_ecode360_client_code,
    extract_ecode360_node_id,
    extract_new_laws_count,
    html_to_hash,
    normalize_text,
    sha256_hex,
)
from app.services.postingest_gate import vendor_cited

_ECODE_PAGE = """
<html><body>
<a href="/DE3083/home">Home</a>
<a href="/DE3083/laws">New Laws (9)</a>
<a href="/DE3083/search">Search</a>
<div class="litem">Chapter 280: Zoning</div>
</body></html>
"""


class TestHostDetection:
    def test_ecode360(self):
        assert detect_host_kind("https://ecode360.com/35078809") == "ecode360"

    def test_municode(self):
        assert detect_host_kind("https://library.municode.com/az/scottsdale/codes/x") == "municode"

    def test_pdf(self):
        assert detect_host_kind("https://town.gov/zoning_bylaw.PDF") == "pdf"

    def test_generic(self):
        assert detect_host_kind("https://www.codepublishing.com/WA/Bellevue/") == "generic_html"


class TestEcodeExtraction:
    def test_client_code(self):
        assert extract_ecode360_client_code(_ECODE_PAGE) == "DE3083"

    def test_client_code_absent(self):
        assert extract_ecode360_client_code("<html>nothing here</html>") is None

    def test_new_laws_badge(self):
        assert extract_new_laws_count(_ECODE_PAGE) == 9

    def test_new_laws_badge_absent(self):
        assert extract_new_laws_count("<html>no badge</html>") is None

    def test_node_id_from_url(self):
        assert extract_ecode360_node_id("https://ecode360.com/8919723") == "8919723"
        assert extract_ecode360_node_id("https://ecode360.com/DE3083/laws") is None


class TestHashing:
    def test_normalize_collapses_whitespace(self):
        assert normalize_text("  a\n\n b\tc  ") == "a b c"

    def test_reflow_does_not_change_hash(self):
        a = html_to_hash("<p>Self-storage   is\na permitted use</p>")
        b = html_to_hash("<div><p>Self-storage is a permitted use</p></div>")
        assert a == b

    def test_script_and_style_ignored(self):
        a = html_to_hash("<p>text</p><script>var cachebuster=123;</script>")
        b = html_to_hash("<p>text</p><script>var cachebuster=456;</script>")
        assert a == b

    def test_content_change_changes_hash(self):
        assert html_to_hash("<p>storage permitted</p>") != html_to_hash("<p>storage prohibited</p>")

    def test_sha256_str_and_bytes(self):
        assert sha256_hex("abc") == sha256_hex(b"abc")
        assert len(sha256_hex("abc")) == 64


class TestDecideDrift:
    def test_first_run_no_baseline_never_drifts(self):
        drifted, reason = decide_drift(
            baseline_hash=None, baseline_new_laws=None, baseline_job_id=None,
            current=Fingerprint(host_kind="ecode360", chapter_hash="a" * 64, new_laws_count=3),
        )
        assert drifted is False and reason is None

    def test_hash_change_drifts(self):
        drifted, reason = decide_drift(
            baseline_hash="a" * 64, baseline_new_laws=None, baseline_job_id=None,
            current=Fingerprint(host_kind="ecode360", chapter_hash="b" * 64),
        )
        assert drifted is True and "chapter text hash changed" in reason

    def test_badge_change_drifts_both_directions(self):
        # laws leaving the badge = just codified — that's drift too
        for new_count in (5, 1):
            drifted, reason = decide_drift(
                baseline_hash=None, baseline_new_laws=3, baseline_job_id=None,
                current=Fingerprint(host_kind="ecode360", new_laws_count=new_count),
            )
            assert drifted is True and f"3 -> {new_count}" in reason

    def test_municode_job_change_drifts_with_stamp(self):
        drifted, reason = decide_drift(
            baseline_hash=None, baseline_new_laws=None, baseline_job_id="425135",
            current=Fingerprint(
                host_kind="municode", municode_job_id="431002",
                codified_through="Codified through Ordinance No. 4700 (Supp. No. 81)",
            ),
        )
        assert drifted is True
        assert "425135 -> 431002" in reason and "Supp. No. 81" in reason

    def test_lost_signal_is_not_drift(self):
        # print endpoint down -> chapter_hash None: must NOT read as drift
        drifted, reason = decide_drift(
            baseline_hash="a" * 64, baseline_new_laws=3, baseline_job_id=None,
            current=Fingerprint(host_kind="ecode360", chapter_hash=None, new_laws_count=3),
        )
        assert drifted is False and reason is None

    def test_stable_everything_no_drift(self):
        drifted, _ = decide_drift(
            baseline_hash="a" * 64, baseline_new_laws=3, baseline_job_id="425135",
            current=Fingerprint(
                host_kind="ecode360", chapter_hash="a" * 64,
                new_laws_count=3, municode_job_id="425135",
            ),
        )
        assert drifted is False


class TestVendorCited:
    def test_zoneomics_citation_flags(self):
        cites = '[{"section": "https://www.zoneomics.com/code/needham-MA", "quote": "..."}]'
        assert vendor_cited(cites) == "zoneomics.com"

    def test_primary_source_citation_clean(self):
        cites = '[{"section": "§ 280-4.2 (ecode360.com/35078809)", "quote": "verbatim text"}]'
        assert vendor_cited(cites) is None

    def test_none_and_empty(self):
        assert vendor_cited(None) is None
        assert vendor_cited("") is None
