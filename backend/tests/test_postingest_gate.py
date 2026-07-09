"""Unit tests for the 2.5 post-ingest gate pure helpers (no DB)."""
from app.services.postingest_gate import (
    GateReport,
    dominant_code,
    is_url_shaped,
)


class TestIsUrlShaped:
    def test_plain_url(self):
        assert is_url_shaped("https://ecode360.com/12345678") is True

    def test_http_url(self):
        assert is_url_shaped("http://example.com") is True

    def test_over_length(self):
        assert is_url_shaped("A" * 21) is True

    def test_normal_code(self):
        assert is_url_shaped("LMA") is False
        assert is_url_shaped("R-10") is False
        assert is_url_shaped("C123") is False

    def test_boundary_length_ok(self):
        assert is_url_shaped("A" * 20) is False  # exactly at limit

    def test_none_and_empty(self):
        assert is_url_shaped(None) is False
        assert is_url_shaped("") is False


class TestDominantCode:
    def test_dominates(self):
        counts = {"B": 9500, "A": 100, "C": 100, "D": 100, "E": 100, "F": 100}
        d = dominant_code(counts)
        assert d is not None and d[0] == "B" and d[1] > 0.9

    def test_too_few_distinct_codes(self):
        # A legit single/few-district town must NOT trip domination
        counts = {"B": 9500, "A": 100}
        assert dominant_code(counts) is None

    def test_no_domination(self):
        counts = {"A": 30, "B": 25, "C": 20, "D": 15, "E": 10}
        assert dominant_code(counts) is None

    def test_empty(self):
        assert dominant_code({}) is None

    def test_at_threshold_not_over(self):
        # exactly 90% does not trip (must be > 90%)
        counts = {"B": 900, "A": 25, "C": 25, "D": 25, "E": 25}  # 900/1000 = 0.90
        assert dominant_code(counts) is None


class TestGateReport:
    def test_fail_flips_passed(self):
        r = GateReport(jurisdiction_id="x")
        assert r.passed is True
        r.fail("bad")
        assert r.passed is False and r.hard_failures == ["bad"]

    def test_warn_keeps_passed(self):
        r = GateReport(jurisdiction_id="x")
        r.warn("meh")
        assert r.passed is True and r.warnings == ["meh"]


class TestSiblingConsistencyCatch58:
    from app.services.postingest_gate import sibling_consistency_violation as _f

    def test_billerica_shaped_trips(self):
        from app.services.postingest_gate import sibling_consistency_violation as f
        # lgc conditional (inferred from li), ss+mw prohibited, no named-garage basis
        basis = "lgc conditional by inference from light_industrial; closed-list; no named garage use"
        assert f("prohibited", "prohibited", "conditional", basis) is True

    def test_marlborough_shaped_does_not_trip(self):
        from app.services.postingest_gate import sibling_consistency_violation as f
        # lgc permitted on the NAMED 'hobby vehicle storage' use — legit, exempt
        basis = "lgc permitted 0.95: 'hobby vehicle storage' named by-right in 650-18A(36)"
        assert f("prohibited", "prohibited", "permitted", basis) is False

    def test_conditional_sibling_not_flagged(self):
        from app.services.postingest_gate import sibling_consistency_violation as f
        # Stoughton/Braintree/Dedham: ss=conditional (not prohibited) => consistent, no trip
        assert f("conditional", "conditional", "conditional", "inferred") is False

    def test_lgc_prohibited_not_flagged(self):
        from app.services.postingest_gate import sibling_consistency_violation as f
        # Billerica/Wilmington post-reconcile: lgc prohibited => nothing to flag
        assert f("prohibited", "prohibited", "prohibited", "any basis") is False

    def test_one_sibling_prohibited_not_enough(self):
        from app.services.postingest_gate import sibling_consistency_violation as f
        # only ss prohibited, mw conditional => not the both-prohibited leak signature
        assert f("prohibited", "conditional", "conditional", "inferred") is False
