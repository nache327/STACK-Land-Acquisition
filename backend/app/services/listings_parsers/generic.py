"""Generic listing parser — expects column headers that match the
canonical ``forsale_listings`` column names verbatim (snake_case).

Useful for tests, hand-curated CSVs, and re-uploading CoStar data
under a different ``source`` tag (e.g. to dry-run a LoopNet UI flow
before the real LoopNet parser exists). The fingerprint always
returns True so it serves as the dispatcher's fallback.
"""
from __future__ import annotations

from app.services.listings_parsers._common import (
    ListingRow,
    ParseResult,
    pick_column,
    to_decimal,
    to_int,
    to_str,
)


_REQUIRED = ("address", "sale_status")


class Parser:
    name = "generic"

    @classmethod
    def fingerprint(cls, columns: list[str]) -> bool:
        # Always last in priority — accepts anything with address + status
        lower = {c.lower().strip() for c in columns}
        return all(req in lower for req in _REQUIRED)

    @classmethod
    def parse_dataframe(cls, df, filename: str) -> ParseResult:
        cols = [str(c).strip() for c in df.columns]

        def col(name: str) -> str | None:
            return pick_column(cols, name)

        warnings: list[str] = []
        if col("address") is None:
            raise ValueError("Generic parser: missing required 'address' column")

        rows: list[ListingRow] = []
        for _, row in df.iterrows():
            raw = {c: row[c] for c in cols if c in row.index}
            raw = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in raw.items()}

            address = to_str(row.get(col("address")))
            if not address:
                continue
            sale_status = to_str(row.get(col("sale_status"))) or "Active"

            rows.append(ListingRow(
                address=address,
                sale_status=sale_status,
                city=to_str(row.get(col("city"))) if col("city") else None,
                state=to_str(row.get(col("state"))) if col("state") else None,
                zip=to_str(row.get(col("zip"))) if col("zip") else None,
                sale_category=to_str(row.get(col("sale_category"))) if col("sale_category") else None,
                property_type=to_str(row.get(col("property_type"))) if col("property_type") else None,
                secondary_type=to_str(row.get(col("secondary_type"))) if col("secondary_type") else None,
                rating=to_int(row.get(col("rating"))) if col("rating") else None,
                size_sf=to_decimal(row.get(col("size_sf"))) if col("size_sf") else None,
                sale_price=to_decimal(row.get(col("sale_price"))) if col("sale_price") else None,
                price_per_sf=to_decimal(row.get(col("price_per_sf"))) if col("price_per_sf") else None,
                cap_rate=to_decimal(row.get(col("cap_rate"))) if col("cap_rate") else None,
                days_on_market=to_int(row.get(col("days_on_market"))) if col("days_on_market") else None,
                sale_type=to_str(row.get(col("sale_type"))) if col("sale_type") else None,
                property_name=to_str(row.get(col("property_name"))) if col("property_name") else None,
                land_area_ac=to_decimal(row.get(col("land_area_ac"))) if col("land_area_ac") else None,
                land_area_sf=to_decimal(row.get(col("land_area_sf"))) if col("land_area_sf") else None,
                price_per_ac=to_decimal(row.get(col("price_per_ac"))) if col("price_per_ac") else None,
                price_per_land_sf=to_decimal(row.get(col("price_per_land_sf"))) if col("price_per_land_sf") else None,
                num_units=to_int(row.get(col("num_units"))) if col("num_units") else None,
                price_per_unit=to_decimal(row.get(col("price_per_unit"))) if col("price_per_unit") else None,
                listing_broker_company=to_str(row.get(col("listing_broker_company"))) if col("listing_broker_company") else None,
                listing_broker_contact=to_str(row.get(col("listing_broker_contact"))) if col("listing_broker_contact") else None,
                listing_broker_phone=to_str(row.get(col("listing_broker_phone"))) if col("listing_broker_phone") else None,
                listing_broker_email=to_str(row.get(col("listing_broker_email"))) if col("listing_broker_email") else None,
                building_class=to_str(row.get(col("building_class"))) if col("building_class") else None,
                zoning_listed=to_str(row.get(col("zoning_listed"))) if col("zoning_listed") else None,
                market=to_str(row.get(col("market"))) if col("market") else None,
                submarket=to_str(row.get(col("submarket"))) if col("submarket") else None,
                county=to_str(row.get(col("county"))) if col("county") else None,
                raw_row=raw,
            ))
        return ParseResult(rows=rows, detected_source="generic", warnings=warnings)


__all__ = ["Parser"]
