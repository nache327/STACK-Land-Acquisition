"""Guard: no text() construct may contain a PHANTOM bind parameter.

SQLAlchemy's bind regex refuses to end a parameter name immediately before a colon, so
``:cities::text[]`` does not parse as ``cities`` -- it parses as the TRUNCATED name
``citie``. The statement then compiles fine and fails only at call time with
"This text() construct doesn't define a bound parameter named 'cities'", or worse binds
a value nobody reads.

That is not hypothetical. It made ``precompute_ring_metrics_for_jurisdiction`` -- and
therefore every ring precompute, the API route, the job-queue path and the dt=10 repair
-- raise before touching the DB, from commit 001a471 until 2026-07-29. No test
referenced the function, so nothing caught it.

The trap also lives inside SQL COMMENTS: text() parses comments too, so writing
"-- use CAST, not :jid::uuid" in a comment reintroduces the phantom. That happened
while fixing the original instance.

A grep cannot see this: only the parser knows what a name resolved to. So this test
compiles every text() literal it can find and asserts the parsed bind names.

Fix a failure by casting with ``CAST(:name AS type)`` instead of ``:name::type``.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text

# A colon-introduced identifier as the SOURCE spells it: a colon not preceded by another
# colon or a word character (so ``centroid::geometry`` is a cast, not a parameter).
_SOURCE_NAME_RE = re.compile(r"(?<![:\w$]):([A-Za-z_][A-Za-z0-9_]*)")

BACKEND = Path(__file__).resolve().parent.parent
SEARCH_DIRS = (BACKEND / "app", BACKEND / "scripts")


def _text_literals(path: Path) -> list[tuple[int, str]]:
    """(lineno, sql) for every text(<string literal>) call in a module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        fn = node.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name != "text":
            continue
        try:
            value = ast.literal_eval(node.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue          # dynamic/f-string SQL: not statically checkable
        if isinstance(value, str):
            out.append((node.lineno, value))
    return out


def _phantoms(sql: str) -> list[str]:
    """Bind names where the SOURCE and the PARSE disagree -- in either direction.

    Two earlier formulations were wrong, which is why the parametrised test below is not
    optional:
      * looking for ``":<parsed>:"`` in the SQL finds NOTHING, because the parsed name is
        already truncated (``citie``, never ``cities``) -- a silent false clean;
      * flagging "a parsed name followed by a word character" FALSE-POSITIVES whenever
        one real parameter name is a prefix of another (``:radius_m`` beside
        ``:radius_miles``).
    """
    try:
        parsed = text(sql)._bindparams.keys()
    except Exception:            # noqa: BLE001 - a construct we cannot compile
        return []
    # Compare what the SOURCE spells against what SQLAlchemy PARSED. Any mismatch in
    # either direction is a phantom:
    #   * a source name missing from parsed  -> the parse truncated it (":cities::text[]")
    #   * a parsed name absent from source   -> a phantom exists, e.g. from a colon
    #     token inside a comment, and will demand a value nobody supplies.
    # Both directions are needed. A one-directional check on "parsed name followed by a
    # word character" produces FALSE POSITIVES when one real parameter name is a prefix
    # of another (":radius_m" alongside ":radius_miles" is perfectly valid).
    source = set(_SOURCE_NAME_RE.findall(sql))
    return sorted(source.symmetric_difference(parsed))


def _python_files() -> list[Path]:
    files: list[Path] = []
    for d in SEARCH_DIRS:
        if d.is_dir():
            files.extend(p for p in d.rglob("*.py") if "/.venv/" not in p.as_posix())
    return files


def test_no_phantom_bindparams_anywhere() -> None:
    offenders: list[str] = []
    checked = 0
    for path in _python_files():
        for lineno, sql in _text_literals(path):
            checked += 1
            phantom = _phantoms(sql)
            if phantom:
                rel = path.relative_to(BACKEND).as_posix()
                offenders.append(
                    f"{rel}:{lineno} parsed {phantom} — a ':name::cast' truncation. "
                    f"Use CAST(:name AS type)."
                )
    assert checked > 50, f"only found {checked} text() literals — the scan is broken"
    assert not offenders, "phantom bind parameters found:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1 WHERE a = ANY(:cities::text[])", ["citie", "cities"]),  # real bug
        ("SELECT 1 WHERE a = :jid::uuid", ["ji", "jid"]),
        ("-- prefer CAST over :jid::uuid\nSELECT 1 WHERE a = :jid", ["ji"]),  # comment
        ("SELECT 1 WHERE a = ANY(CAST(:cities AS text[]))", []),  # the fix
        # prefix-collision: two REAL names, one a prefix of the other. Must be clean.
        ("SELECT 1 FROM t WHERE ST_DWithin(a, b, :radius_m) AND r = :radius_miles", []),
        ("SELECT ST_Extent(centroid::geometry) FROM t WHERE id = :jid", []),  # col cast
    ],
)
def test_detector_catches_the_shapes_it_must(sql: str, expected: list[str]) -> None:
    """The detector itself must not be a test that asserts nothing.

    Includes a plain column cast (``centroid::geometry``), which is legitimate and must
    NOT be flagged, and a colon token inside a comment, which must be.
    """
    assert _phantoms(sql) == expected
