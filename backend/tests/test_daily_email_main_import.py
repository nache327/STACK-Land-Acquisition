"""Running daily_email as `python -m` must not break the dashboard_push import.

Regression: the cron executes `python -m app.workers.daily_email`; run_once()
then imports app.services.dashboard_push, which imports app.workers.daily_email
again. Without the __main__ alias that second copy re-registers the dramatiq
actor ('send_daily_digest_actor' is already registered) and every scheduled
board push failed silently.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

_PROBE = r"""
import runpy, sys
sys.argv = ["daily_email", "--help"]
try:
    runpy.run_module("app.workers.daily_email", run_name="__main__", alter_sys=True)
except SystemExit:
    pass  # argparse --help exits after the module body (and the alias) ran
import app.services.dashboard_push  # must not raise "actor ... already registered"
print("IMPORT_OK")
"""


def test_dashboard_push_imports_when_daily_email_runs_as_main():
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=BACKEND, capture_output=True, text=True, timeout=120,
    )
    assert "IMPORT_OK" in proc.stdout, proc.stderr[-2000:]
