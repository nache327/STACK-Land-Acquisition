from app.services.ordinance_fetcher import (
    OrdinanceSection,
    _looks_like_ordinance_text,
    detect_source_type,
)
from scripts.retrieve_ordinance_excerpts import Target, _best_excerpt


def test_detects_supported_code_hosts():
    assert detect_source_type("https://bellevue.municipal.codes/LUC/20.10.440") == "municipal_codes"
    assert detect_source_type("https://www.codepublishing.com/WA/Test/html/Test.html") == "code_publishing"
    assert detect_source_type("https://library.municode.com/mn/edina/codes/code") == "municode"
    assert detect_source_type("https://codelibrary.amlegal.com/codes/test/latest/test/0-0-0-1") == "american_legal"
    assert detect_source_type("https://online.encodeplus.com/regs/test") == "encodeplus"


def test_rejects_challenge_shells_as_not_ordinance_text():
    assert not _looks_like_ordinance_text("Just a moment...\nEnable JavaScript and cookies")
    assert not _looks_like_ordinance_text("Content Not Found")
    assert _looks_like_ordinance_text(
        "Sec. 36-640. Principal uses. The following are principal uses permitted "
        "in the Planned Industrial District. " * 4
    )


def test_best_excerpt_prefers_matching_section():
    target = Target(
        slug="edina",
        label="Edina test",
        url="https://library.municode.com/example",
        section="36-640",
        keywords=("mini-storage",),
    )
    sections = [
        OrdinanceSection("36-401", "Classification", "Residential district text."),
        OrdinanceSection(
            "36-640",
            "Principal uses",
            "The following are principal uses permitted in the Planned Industrial District: "
            "Mini-storage warehouses.",
            ["PID"],
        ),
    ]

    excerpt = _best_excerpt(sections, target, 1_000)

    assert "Matched section: 36-640" in excerpt
    assert "Mini-storage warehouses" in excerpt
