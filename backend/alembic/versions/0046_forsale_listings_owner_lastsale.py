"""Owner contact + last-sale columns on forsale_listings (columns ONLY).

The CoStar reports carry owner + prior-sale data (Owner Name/Phone/Contact/
Address, Recorded Owner *, Last Sale Price/Date) that the parser previously
dropped (only surviving in raw_row JSONB). These columns let the app display
owner contact + last-sale in the parcel drawer's ListingCard for Stage-4
outreach, mirroring the existing broker/sale-price fields.

0042/0045 LESSON APPLIED: no data backfill here — existing rows are
backfilled from raw_row by scripts/_backfill_listing_owner_from_raw.py.
Nullable/no-default = instant DDL.

Revision ID: 0046
Revises: 0045
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET statement_timeout = 0")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS owner_name TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS owner_phone TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS owner_contact TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS owner_address TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS recorded_owner_name TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS recorded_owner_phone TEXT NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS last_sale_price NUMERIC NULL")
    op.execute("ALTER TABLE forsale_listings ADD COLUMN IF NOT EXISTS last_sale_date DATE NULL")


def downgrade() -> None:
    for col in (
        "owner_name", "owner_phone", "owner_contact", "owner_address",
        "recorded_owner_name", "recorded_owner_phone", "last_sale_price", "last_sale_date",
    ):
        op.execute(f"ALTER TABLE forsale_listings DROP COLUMN IF EXISTS {col}")
