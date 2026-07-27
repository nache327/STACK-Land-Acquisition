"""ops_job_run: server-side record of long maintenance jobs.

Long data jobs (radial backfills, full re-scores, ring recomputes) used to be
orchestrated from Nache's laptop, which meant they died when the machine slept —
an 8-hour job could never use the overnight window, and one overnight run lost 9
of 151 counties that way. They now run in the Railway dramatiq worker; this table
is how their progress is observable from outside that process.

Deliberately mirrors the shape the audit called out as the right pattern (the
dashboard's push_run + ops_cron_heartbeat): one row per run, a status, and enough
output retained to diagnose a failure without shelling into the container.

Light + idempotent: Railway runs `alembic upgrade head` as a pre-deploy command,
so a heavy migration aborts the rollout (see railway.toml).

Revision ID: 0055
Revises: 0054
"""
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops_job_run (
            id           BIGSERIAL PRIMARY KEY,
            job_name     TEXT        NOT NULL,
            args         JSONB       NOT NULL DEFAULT '{}'::jsonb,
            status       TEXT        NOT NULL DEFAULT 'queued',
            queued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at   TIMESTAMPTZ,
            finished_at  TIMESTAMPTZ,
            exit_code    INTEGER,
            -- Rolling tail of stdout/stderr. Bounded in the writer so a chatty
            -- multi-hour job cannot grow this row without limit.
            log_tail     TEXT,
            -- Last progress line the job emitted, for cheap polling.
            progress     TEXT,
            error        TEXT
        )
        """
    )
    # Status/queue lookups: "is anything running?" and "show me recent runs".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ops_job_run_status_queued "
        "ON ops_job_run (status, queued_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ops_job_run_status_queued")
    op.execute("DROP TABLE IF EXISTS ops_job_run")
