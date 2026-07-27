"""The maintenance job runner must never become a remote shell.

It is reachable over HTTP (admin-secret gated) and spawns subprocesses, so the
security properties below are the whole reason it is safe to expose. Each of
these guards a way the surface could be widened by accident later.
"""
from __future__ import annotations

import sys

import pytest

from app.services.maintenance_jobs import JOBS, resolve


def test_only_allowlisted_job_names_resolve():
    with pytest.raises(ValueError):
        resolve("definitely_not_a_job", {})
    # ...and the error names the allowlist, so the 400 is actionable
    try:
        resolve("definitely_not_a_job", {})
    except ValueError as e:
        assert "allowed" in str(e)


def test_no_shell_and_interpreter_is_ours():
    """argv[0] must be this interpreter, never a shell or a bare name resolved
    off PATH."""
    argv = resolve("rescore_all", {})
    assert argv[0] == sys.executable
    assert argv[1] == "-u"
    assert argv[2].endswith("rescore_all_jurisdictions.py")


@pytest.mark.parametrize("evil", [
    "; rm -rf /",
    "$(whoami)",
    "`id`",
    "&& curl http://evil",
    "../../etc/passwd",
    "--some-other-flag",
    "00000000-0000-0000-0000-000000000000 --extra",
])
def test_uuid_params_reject_injection(evil):
    """A jurisdiction is parsed as a real UUID, so nothing that looks like a
    flag, a path, or a shell fragment can reach argv."""
    with pytest.raises(Exception):
        resolve("rescore_all", {"jurisdiction": evil})


def test_uuid_is_canonicalised_not_passed_through():
    """Even a valid-but-oddly-formatted UUID is re-emitted canonically."""
    argv = resolve("rescore_all", {"jurisdiction": "0000000000004000800000000000000A"})
    assert "--jurisdiction" in argv
    assert argv[argv.index("--jurisdiction") + 1] == "00000000-0000-4000-8000-00000000000a"


@pytest.mark.parametrize("args", [
    {"start_index": -1},
    {"start_index": 10**9},
    {"retries": 0},
    {"retries": 10**6},
])
def test_numeric_params_are_range_checked(args):
    with pytest.raises(Exception):
        resolve("rescore_all", args)


@pytest.mark.parametrize("args", [
    {"grid_deg": 0},
    {"grid_deg": 99},
    {"redo_after": "not-a-timestamp"},
])
def test_backfill_params_are_validated(args):
    with pytest.raises(Exception):
        resolve("backfill_radial", args)


def test_unknown_arg_keys_are_dropped_not_forwarded():
    """A caller cannot smuggle extra flags through by inventing a key."""
    assert resolve("rescore_all", {"evil": "--wipe-everything"})[3:] == []
    assert resolve("pop_band_delta", {"anything": "at-all"})[3:] == []


def test_booleans_emit_flags_not_values():
    argv = resolve("backfill_radial",
                   {"area_weighted": True, "redo": True, "skip_saturation": True})
    assert argv[3:] == ["--area-weighted", "--redo", "--skip-saturation"]
    # falsy -> flag absent entirely
    assert resolve("backfill_radial", {"area_weighted": False})[3:] == []


def test_every_registered_job_points_at_an_existing_script():
    """A typo'd filename would only surface when someone tried to run it."""
    for name in JOBS:
        argv = resolve(name, {})   # raises if the script is missing
        assert argv[2].endswith(".py")
