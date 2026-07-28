"""Index parcel_buybox_scores(buybox_filter_id, computed_at) — audit item A-9.

WHY: every freshness/coverage question we ask of this table filters on
buybox_filter_id AND ranges on computed_at, and no index covered that pair. The
existing ix_pbs_filter_score is (buybox_filter_id, score) — useless for a
computed_at range. So every such query SEQ-SCANNED a ~50M-row table.

Measured cost of not having it, all on 2026-07-28:
  * the count-based coverage audit issued 302 of those queries and took ~90 min;
  * rewritten as ONE grouped pass it still took ~11 min;
  * report_pop_band_board_delta.py (Gate B) ran 28 min on its FIRST of ~6 such
    queries before we gave up and built this.

CONCURRENTLY + an autocommit block: prod is live, and a plain CREATE INDEX takes
an ACCESS EXCLUSIVE lock that would stall the board and the digest for the
duration of a 50M-row build. CONCURRENTLY cannot run inside a transaction, and
Alembic wraps migrations in one by default, hence the explicit autocommit_block.

IF NOT EXISTS because the index was built by hand on prod first (to unblock Gate
B) and this migration then banks it in the schema. Railway runs `alembic upgrade
head` at BOOT, so a migration that rebuilt a 50M-row index there would stall or
crashloop the deploy — this one is a no-op when the index already exists.

Down-migration also uses CONCURRENTLY, for the same live-prod reason.
"""
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_INDEX = "ix_pbs_filter_computed_at"
_TABLE = "parcel_buybox_scores"


def upgrade() -> None:
    # autocommit_block: CONCURRENTLY is invalid inside Alembic's transaction.
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
            f"ON {_TABLE} (buybox_filter_id, computed_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
