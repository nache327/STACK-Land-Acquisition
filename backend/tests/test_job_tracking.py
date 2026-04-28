from app.services.job_tracking import normalize_dedupe_key, truncate_error


def test_normalize_dedupe_key_is_stable_for_spacing_and_use_order() -> None:
    a = normalize_dedupe_key(
        "  Draper,   UT ",
        ["mini_warehouse", "self_storage"],
        "HTTPS://Example.com/Code",
    )
    b = normalize_dedupe_key(
        "draper, UT",
        ["self_storage", "mini_warehouse"],
        "https://example.com/code",
    )

    assert a == b


def test_truncate_error_caps_long_messages() -> None:
    assert truncate_error("x" * 20, max_length=10) == "xxxxxxxxxx... [truncated]"
