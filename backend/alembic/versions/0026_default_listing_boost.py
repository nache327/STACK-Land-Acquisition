"""Bump default listingScoreBoost from 0 -> 15

The for-sale-listings feature (Layer 4) introduces a `listingScoreBoost`
factor in `score_for_parcel`. When set, parcels with a current matched
listing get N points added so they naturally rise to the top of the
daily digest. The original default was 0 (boost off), since we wanted
the feature behind an opt-in toggle. After verifying listings ingestion
works end-to-end (73% match rate on Lehi), the default is bumped to 15
so new and existing saved filters surface listed parcels by default.

Rule (must be respected for future readers):

  Bump ``listingScoreBoost`` from 0 or NULL to 15 on all existing
  ``buybox_filters`` rows. User-customized non-zero values are
  preserved.

Single-user prod today, but the rule above governs any future
multi-tenant rollout of this migration. The WHERE clause encodes it
literally: only rows where the key is absent OR equal to 0 are
updated.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # JSONB merge: set the key only when missing or zero. User-customized
    # non-zero values (e.g. 25, 50) survive untouched.
    op.execute(
        """
        UPDATE buybox_filters
           SET filter_json = filter_json || jsonb_build_object('listingScoreBoost', 15)
         WHERE
            -- key not present at all
            (NOT (filter_json ? 'listingScoreBoost'))
            -- or present but zero / null
            OR (filter_json ->> 'listingScoreBoost') IS NULL
            OR (filter_json ->> 'listingScoreBoost')::int = 0
        """
    )


def downgrade() -> None:
    # Best-effort revert: remove the key entirely. We can't tell which
    # rows had it set to 15 by us vs by the user, so the safe move is
    # to drop it everywhere — DEFAULT_FILTER in frontend will fill in
    # whatever the current default is.
    op.execute(
        """
        UPDATE buybox_filters
           SET filter_json = filter_json - 'listingScoreBoost'
         WHERE filter_json ? 'listingScoreBoost'
        """
    )
