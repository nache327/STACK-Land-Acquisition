"""parcels.in_flood_zone / in_wetland: drop NOT NULL

Phase 3 — DC/Mid-Atlantic counties. Source FeatureServers for VA/MD/PA/NY/NJ/CT
do not publish a flood field, so the ingester now writes in_flood_zone=NULL
(signalling apply_flood_overlay to compute the bool spatially against FEMA
NFHL). The original schema enforced NOT NULL with server_default=false, which
masked the missing-data case as "definitely not in flood zone" — that's what
left every NJ Phase 1 county with flood_true=0 even where SFHA polygons exist.

This migration drops NOT NULL on both flood + wetland flags. Existing False
rows stay valid; new None rows are now allowed and gate the spatial overlay.
"""
from alembic import op


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE parcels ALTER COLUMN in_flood_zone DROP NOT NULL")
    op.execute("ALTER TABLE parcels ALTER COLUMN in_wetland   DROP NOT NULL")


def downgrade() -> None:
    op.execute(
        "UPDATE parcels SET in_flood_zone = FALSE WHERE in_flood_zone IS NULL"
    )
    op.execute(
        "UPDATE parcels SET in_wetland = FALSE WHERE in_wetland IS NULL"
    )
    op.execute("ALTER TABLE parcels ALTER COLUMN in_flood_zone SET NOT NULL")
    op.execute("ALTER TABLE parcels ALTER COLUMN in_wetland   SET NOT NULL")
