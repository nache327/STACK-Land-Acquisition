"""2.3 parser guards — LLM output is untrusted until proven against parcel
codes and the source text. Billerica (Oct 2025 bylaw) is the acceptance
jurisdiction for the live path; these unit tests pin the guard semantics."""
import json

from app.services.ordinance_parser import (
    MAX_INPUT_CHARS,
    _apply_output_guards,
    _build_output,
)
from app.schemas.zone_use_matrix import ParserOutput, ParserZoneResult


SOURCE = (
    "Section 8.1 Table of Uses. In the I Industrial District, warehouses are "
    "permitted by right. Self-storage facilities require a special permit in "
    "the SS overlay. The GB General Business district allows retail."
)


def _zone(code, **over):
    d = dict(
        code=code,
        self_storage="prohibited",
        mini_warehouse="prohibited",
        light_industrial="permitted",
        luxury_garage_condo="prohibited",
        citations=[],
        confidence=0.9,
        notes=None,
    )
    d.update(over)
    return d


def _out(zones, unknown=None, warnings=None):
    return ParserOutput(
        zones=[ParserZoneResult.model_validate(z) for z in zones],
        unknown_zones=unknown or [],
        parser_warnings=warnings or [],
    )


class TestMembershipGuard:
    def test_unknown_code_routed_to_unknown_zones(self):
        out = _apply_output_guards(_out([_zone("I"), _zone("ZZ-9")]), ["I", "GB"], SOURCE)
        assert [z.code for z in out.zones] == ["I"]
        assert "ZZ-9" in out.unknown_zones
        assert any("membership" in w for w in out.parser_warnings)

    def test_membership_is_normalized(self):
        # "i-g" should match known code "IG" (case / dash / space insensitive)
        out = _apply_output_guards(_out([_zone("i-g")]), ["IG"], SOURCE)
        assert [z.code for z in out.zones] == ["i-g"]
        assert out.unknown_zones == []

    def test_composite_known_codes_are_split(self):
        out = _apply_output_guards(_out([_zone("CC")]), ["A5; CC; RM2"], SOURCE)
        assert [z.code for z in out.zones] == ["CC"]

    def test_no_known_codes_disables_guard(self):
        out = _apply_output_guards(_out([_zone("ANY")]), [], SOURCE)
        assert [z.code for z in out.zones] == ["ANY"]


class TestQuoteGuard:
    def test_verbatim_quote_survives(self):
        z = _zone("I", citations=[{"section": "8.1", "quote": "warehouses are permitted by right"}])
        out = _apply_output_guards(_out([z]), ["I"], SOURCE)
        assert len(out.zones[0].citations) == 1
        assert out.zones[0].confidence == 0.9

    def test_whitespace_differences_tolerated(self):
        z = _zone("I", citations=[{"section": "8.1", "quote": "warehouses  are\npermitted   by right"}])
        out = _apply_output_guards(_out([z]), ["I"], SOURCE)
        assert len(out.zones[0].citations) == 1

    def test_fabricated_quote_dropped_and_confidence_capped(self):
        z = _zone("I", citations=[{"section": "8.1", "quote": "self-storage is permitted by right everywhere"}])
        out = _apply_output_guards(_out([z]), ["I"], SOURCE)
        assert out.zones[0].citations == []
        assert out.zones[0].confidence == 0.5
        assert "[guard: all citations failed verbatim check]" in (out.zones[0].notes or "")
        assert any("quote" in w for w in out.parser_warnings)

    def test_one_bad_quote_does_not_cap_when_another_survives(self):
        z = _zone("I", citations=[
            {"section": "8.1", "quote": "warehouses are permitted by right"},
            {"section": "9.9", "quote": "totally fabricated text"},
        ])
        out = _apply_output_guards(_out([z]), ["I"], SOURCE)
        assert len(out.zones[0].citations) == 1
        assert out.zones[0].confidence == 0.9


class TestSilenceGuard:
    def test_truncated_and_unseen_prohibited_downgrades_to_unclear(self):
        long_text = SOURCE + "x" * (MAX_INPUT_CHARS + 10)
        # "MW" never appears in the first MAX_INPUT_CHARS
        out = _apply_output_guards(_out([_zone("MW")]), ["MW"], long_text)
        z = out.zones[0]
        assert z.self_storage == "unclear"
        assert z.luxury_garage_condo == "unclear"
        assert z.light_industrial == "permitted"  # non-prohibited untouched
        assert any("silence" in w for w in out.parser_warnings)

    def test_not_truncated_keeps_prohibited(self):
        out = _apply_output_guards(_out([_zone("MW")]), ["MW"], SOURCE)
        assert out.zones[0].self_storage == "prohibited"

    def test_truncated_but_seen_keeps_prohibited(self):
        long_text = SOURCE + "x" * (MAX_INPUT_CHARS + 10)
        out = _apply_output_guards(_out([_zone("I")]), ["I"], long_text)
        assert out.zones[0].self_storage == "prohibited"


class TestBuildOutputWiring:
    def test_build_output_applies_guards(self):
        raw = json.dumps({
            "zones": [_zone("I"), _zone("HALLUCINATED")],
            "unknown_zones": [],
            "parser_warnings": [],
        })
        out = _build_output(raw, ["I"], SOURCE)
        assert [z.code for z in out.zones] == ["I"]
        assert "HALLUCINATED" in out.unknown_zones

    def test_build_output_without_context_skips_guards(self):
        raw = json.dumps({
            "zones": [_zone("HALLUCINATED")],
            "unknown_zones": [],
            "parser_warnings": [],
        })
        out = _build_output(raw)
        assert [z.code for z in out.zones] == ["HALLUCINATED"]
