"""parcels.owner_mailing_address / owner_mailing_csz — direct-mail enrichment

Bucket A of the owner-mailing backfill audit (2026-07-22): the owner's MAILING
address (distinct from the situs/parcel address) is preserved inside
``parcels.raw`` for the ~16 sources whose ingest kept the full source row. This
adds the two columns the backfill script promotes it into:

  * owner_mailing_address — the mailing street line (may be a PO box)
  * owner_mailing_csz     — the mailing city / state / zip line

Both nullable, no default → instant metadata-only ADD COLUMN, safe at Railway
boot even on the multi-million-row parcels table. Population is a separate
manual data script (scripts/_backfill_parcel_owner_mailing.py), NOT run here, so
this migration does no heavy work at boot.

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-22 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "parcels",
        sa.Column("owner_mailing_address", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "parcels",
        sa.Column("owner_mailing_csz", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("parcels", "owner_mailing_csz")
    op.drop_column("parcels", "owner_mailing_address")
