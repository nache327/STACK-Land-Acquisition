"""Resolve the deployed commit SHA for boot logging.

Order of precedence:
  1. RAILWAY_GIT_COMMIT_SHA  — Railway-injected at deploy
  2. GIT_SHA                  — generic / Docker --build-arg
  3. FLY_IMAGE_REF            — Fly.io image reference
  4. `git rev-parse HEAD`     — local dev only (no .git in container)
  5. "unknown"
"""
from __future__ import annotations

import os
import subprocess


def get_pipeline_version() -> str:
    for env_var in ("RAILWAY_GIT_COMMIT_SHA", "GIT_SHA"):
        value = os.getenv(env_var)
        if value:
            return value[:12]
    fly_ref = os.getenv("FLY_IMAGE_REF")
    if fly_ref:
        return fly_ref
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"
