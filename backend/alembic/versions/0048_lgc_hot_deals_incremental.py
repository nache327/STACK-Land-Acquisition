"""Mark the "LGC Hot deals" preset as incremental-only.

Phase 1c of the LGC roadmap. The digest + listing-alert workers honor a new
``excludeStorageViable`` filter_json flag: when set, the LGC email lane drops
any parcel where storage is itself viable, so a both-viable parcel emails once
(via the storage lane), never twice. This migration sets that flag on the
"LGC Hot deals" preset seeded in 0047.

Idempotent: a jsonb merge (``||``) that overwrites just the one key. Leaves
``daily_email_enabled`` false — the operator still opts the lane in explicitly
after a smoke test; this only shapes WHAT it selects, never whether it sends.

The "LGC Default Box" is intentionally left alone (no excludeStorageViable): the
dashboard asset toggle should show ALL LGC-viable parcels, not just the
incremental pool.

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
LGC_USE_CASE_ID = "00000000-0000-0000-0000-000000000003"
LGC_HOT_DEALS_NAME = "LGC Hot deals"


def upgrade() -> None:
    op.execute(sa.text(
        f"""
        UPDATE buybox_filters
           SET filter_json = filter_json || '{{"excludeStorageViable": true}}'::jsonb
         WHERE organization_id = '{DEFAULT_ORG_ID}'::uuid
           AND use_case_id     = '{LGC_USE_CASE_ID}'::uuid
           AND name            = '{LGC_HOT_DEALS_NAME}'
        """
    ))


def downgrade() -> None:
    op.execute(sa.text(
        f"""
        UPDATE buybox_filters
           SET filter_json = filter_json - 'excludeStorageViable'
         WHERE organization_id = '{DEFAULT_ORG_ID}'::uuid
           AND use_case_id     = '{LGC_USE_CASE_ID}'::uuid
           AND name            = '{LGC_HOT_DEALS_NAME}'
        """
    ))
