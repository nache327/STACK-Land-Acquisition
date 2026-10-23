"""DB DSN helper for the repo-root scripts/*.

NEVER hardcode credentials in a script. This delegates to backend/scripts/_db.py
(DATABASE_URL from the environment, else backend/.env via pydantic settings), so
root and backend scripts share one source of truth.

    from _db import get_sync_dsn
    conn = await asyncpg.connect(get_sync_dsn())   # session-mode 5432
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts._db import get_dsn, get_sync_dsn  # noqa: E402,F401
