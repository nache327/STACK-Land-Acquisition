"""Seed the luxury_garage_condo (LGC) use case + its default buy-box filters.

Phase 1b of the LGC roadmap (docs/AUDIT_2026_07_17.md). Makes LGC a first-class
scored asset alongside self_storage. Seeds three rows, all idempotent:

  1. use_cases row (stable id …0003, slug 'luxury_garage_condo').
  2. "LGC Default Box" buy-box filter — is_default=true for (default org × LGC
     use case). The scorer's auto_score loop + the /scores endpoint resolve it
     by (org, use_case, is_default), and it coexists with the self_storage
     Default Box because uq_buybox_filters_one_default is partial-unique per
     (org, use_case). daily_email_enabled=false — the digest never picks it up
     until the operator opts in (Phase 1c).
  3. "LGC Hot deals" preset — requireListed=true, listing boost, but
     daily_email_enabled=false initially, so a migration can never start
     emailing by surprise. The operator flips it on via PATCH after a smoke
     test.

Thresholds mirror the self_storage Default Box / Hot deals snapshot (pop 50K /
hhi $100K / home $475K / hnw 4400, drive-time 10, listingScoreBoost 15). The
zoning verdict, not the demographics, is what differs between the two assets —
and that lives in the scorer (use_verdicts.py), not the filter_json.

No backfill here (Railway runs alembic at boot; keep migrations light). After
deploy, one POST /api/buybox-filters/{lgc_default_id}/_score-all populates LGC
scores for every existing jurisdiction; new ingests are covered by
auto_score_jurisdiction, which now loops all default filters.

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-17 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
LGC_USE_CASE_ID = "00000000-0000-0000-0000-000000000003"
LGC_DEFAULT_NAME = "LGC Default Box"
LGC_HOT_DEALS_NAME = "LGC Hot deals"

# Shared demographic thresholds — identical to the self_storage snapshot.
_THRESHOLDS = """
    'minPopulation',       50000,
    'minMedianHHI',        100000,
    'minMedianHomeValue',  475000,
    'minHnwHouseholds',    4400,
    'minAADT',             null,
    'minHomesOver1M',      null,
    'minHomesOver2M',      null,
    'minHomesOver5M',      null,
    'sortListedFirst',     false,
    'driveTimeMinutes',    10,
    'matchLogic',          'AND'
"""


def upgrade() -> None:
    # 1. Use case (system-defined: organization_id NULL, visible to all orgs).
    op.execute(sa.text(
        f"""
        INSERT INTO use_cases (id, organization_id, slug, name, description, use_keys)
        VALUES (
            '{LGC_USE_CASE_ID}'::uuid,
            NULL,
            'luxury_garage_condo',
            'Luxury Garage Condo',
            'Luxury garage condominium site selection. Verdict is derived from '
            'the self_storage / mini_warehouse / light_industrial columns at '
            'scoring time (see services/use_verdicts.py), not the stored '
            'luxury_garage_condo column.',
            '["self_storage", "mini_warehouse", "light_industrial"]'::jsonb
        )
        ON CONFLICT DO NOTHING
        """
    ))

    # 2. LGC Default Box — the dashboard/scorer default for the LGC use case.
    op.execute(sa.text(
        f"""
        INSERT INTO buybox_filters (
            organization_id, use_case_id, name, filter_json,
            is_default, daily_email_enabled, daily_email_top_n
        )
        VALUES (
            '{DEFAULT_ORG_ID}'::uuid,
            '{LGC_USE_CASE_ID}'::uuid,
            '{LGC_DEFAULT_NAME}',
            jsonb_build_object(
                {_THRESHOLDS},
                'requireListed',     false,
                'listingScoreBoost',  15
            ),
            true,
            false,
            10
        )
        ON CONFLICT ON CONSTRAINT uq_buybox_filters_org_use_name DO NOTHING
        """
    ))

    # 3. LGC Hot deals preset — email OFF until the operator opts in.
    op.execute(sa.text(
        f"""
        INSERT INTO buybox_filters (
            organization_id, use_case_id, name, filter_json,
            is_default, daily_email_enabled, daily_email_top_n
        )
        VALUES (
            '{DEFAULT_ORG_ID}'::uuid,
            '{LGC_USE_CASE_ID}'::uuid,
            '{LGC_HOT_DEALS_NAME}',
            jsonb_build_object(
                {_THRESHOLDS},
                'requireListed',     true,
                'listingScoreBoost',  15
            ),
            false,
            false,
            10
        )
        ON CONFLICT ON CONSTRAINT uq_buybox_filters_org_use_name DO NOTHING
        """
    ))


def downgrade() -> None:
    op.execute(sa.text(
        f"""
        DELETE FROM buybox_filters
         WHERE organization_id = '{DEFAULT_ORG_ID}'::uuid
           AND use_case_id     = '{LGC_USE_CASE_ID}'::uuid
        """
    ))
    op.execute(sa.text(
        f"DELETE FROM use_cases WHERE id = '{LGC_USE_CASE_ID}'::uuid"
    ))
