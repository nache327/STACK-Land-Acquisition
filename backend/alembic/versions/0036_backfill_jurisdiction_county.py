"""Backfill jurisdictions.county for UT cities.

Why:
    The county field was unreliable for sibling discovery — of 19 SLC-area
    UT cities, most had county=NULL and the rest were split between
    'Salt Lake' and 'Salt Lake County'. zone_matrix_crosswalk works
    around this by using parcels.city instead, but other code paths
    (nj_municipal_discovery, zoning_discovery, dashboard breadcrumbs)
    still read jurisdictions.county and benefit from a clean value.

Two passes:

  1. Normalize trailing ' County' suffix off all UT county values so
     'Salt Lake County' becomes 'Salt Lake' (matches the form the SLCo
     county jurisdiction itself uses, and the form 'salt_lake' lookups
     in pipeline.py expect).

  2. Set county='Salt Lake' on the 15 SLC-area cities currently NULL.
     Hard-coded list — only touches rows where county IS NULL so we
     never overwrite an existing value. Other counties (Utah, Davis,
     Weber, …) can be backfilled the same way as they come up; out of
     scope here.

Idempotent. Re-running is a no-op once the values are correct.

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-28 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# SLC-area cities whose jurisdiction.name matches these strings get
# county='Salt Lake' if their county is currently NULL. List built from
# the parcels.city set we observed under the SLCounty county jurisdiction
# plus the per-city UT jurisdictions known to exist.
SLC_CITY_NAMES = (
    "Bluffdale, UT",
    "Cottonwood Heights, UT",
    "Draper City, UT",      # name retained as-is; crosswalk matches via normalization
    "Herriman, UT",
    "Holladay, UT",
    "Midvale, UT",
    "Millcreek, UT",
    "Murray, UT",
    "Salt Lake City, UT",
    "Sandy, UT",
    "South Jordan, UT",
    "South Salt Lake, UT",
    "Taylorsville, UT",
    "West Jordan, UT",
    "West Valley City, UT",
)


def upgrade() -> None:
    # Pass 1: normalize trailing ' County' on UT county values.
    op.execute(
        """
        UPDATE jurisdictions
           SET county = regexp_replace(county, ' County$', '')
         WHERE state = 'UT'
           AND county LIKE '% County'
        """
    )

    # Pass 2: backfill NULL county on known SLC-area cities.
    name_list = ",".join(f"'{n}'" for n in SLC_CITY_NAMES)
    op.execute(
        f"""
        UPDATE jurisdictions
           SET county = 'Salt Lake'
         WHERE state = 'UT'
           AND county IS NULL
           AND name IN ({name_list})
        """
    )


def downgrade() -> None:
    # No clean reverse — we don't track which rows we set vs which were
    # already 'Salt Lake'. A downgrade would only blank rows we touched
    # in pass 2; we'd need to record them to be precise. Skipping.
    pass
