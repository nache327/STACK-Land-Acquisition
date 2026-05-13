"""forsale_listings.co_listed_parcels — same-owner cluster matches

When the matcher's nearest-parcel tier (within 100m of the geocoded
point) sees multiple parcels sharing the same owner_name as the
"primary" parcel, all of them are recorded in this JSONB column.
Models the real-world case where a single CoStar listing represents
two or more adjacent lots that the owner is selling together.

Shape:
    [
      {"id": 12345, "apn": "...", "acres": 5.2, "is_primary": true},
      {"id": 12346, "apn": "...", "acres": 3.1, "is_primary": false},
      ...
    ]

NULL when matching produced a single-parcel hit (the common case).

Also adds an index on owner_name to keep the cluster-detection
lookup fast at million-parcel scale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "forsale_listings",
        sa.Column("co_listed_parcels", JSONB, nullable=True),
    )
    # Owner-name lookup for cluster detection. The matcher does:
    #   SELECT id, acres FROM parcels
    #    WHERE jurisdiction_id = $1 AND owner_name = $2
    #      AND ST_DWithin(centroid, $3, 100)
    # so an index on (jurisdiction_id, owner_name) is the right shape.
    op.create_index(
        "ix_parcels_jurisdiction_owner",
        "parcels",
        ["jurisdiction_id", "owner_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_parcels_jurisdiction_owner", table_name="parcels")
    op.drop_column("forsale_listings", "co_listed_parcels")
