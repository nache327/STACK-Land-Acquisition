"""CoStar export parser.

Column mapping is the best-guess against industry-standard CoStar
sale exports. Refine after the first real ``Lehi.xlsx`` lands in
``backend/uploads/`` — the test
``backend/tests/test_listings_costar_parser.py`` will fail loudly on
any column-name mismatch and tell you what needs to move.
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


# CoStar fingerprint columns — these almost always appear in their
# sale exports. ANY two of them present is enough to declare CoStar.
_FINGERPRINT_COLUMNS = (
    "Days On Market",
    "Sale Status",
    "Building SF",
    "Listing Broker Company",
    "Submarket Name",
    "CoStar Property ID",
)


class Parser:
    name = "costar"

    @classmethod
    def fingerprint(cls, columns: list[str]) -> bool:
        lower = {c.lower().strip() for c in columns}
        matches = sum(1 for fp in _FINGERPRINT_COLUMNS if fp.lower() in lower)
        return matches >= 2

    @classmethod
    def parse_dataframe(cls, df, filename: str) -> ParseResult:
        cols = [str(c).strip() for c in df.columns]

        # Column aliases — first wins. CoStar exports vary slightly
        # across user-configured templates, so we accept a few names.
        col_address  = pick_column(cols, "Property Address", "Property Address Line 1", "Address")
        col_city     = pick_column(cols, "City")
        col_state    = pick_column(cols, "State")
        col_zip      = pick_column(cols, "Zip", "Zip Code", "Postal Code")
        col_status   = pick_column(cols, "Sale Status", "Status")
        col_category = pick_column(cols, "Sale Category")
        col_ptype    = pick_column(cols, "Property Type")
        col_stype    = pick_column(cols, "Secondary Type")
        col_rating   = pick_column(cols, "Rating", "Star Rating")
        col_size     = pick_column(cols, "Building SF", "Size SF", "RBA")
        col_price    = pick_column(cols, "Sale Price", "Sale Price ($)")
        col_psf      = pick_column(cols, "Price Per SF", "Sale Price/SF")
        col_cap      = pick_column(cols, "Cap Rate", "Sale Cap Rate")
        col_dom      = pick_column(cols, "Days On Market", "DOM")
        col_stype2   = pick_column(cols, "Sale Type")
        col_pname    = pick_column(cols, "Property Name", "Building Name")
        col_land_ac  = pick_column(cols, "Land Area AC", "Land Area Acres")
        col_land_sf  = pick_column(cols, "Land Area SF")
        col_ppac     = pick_column(cols, "Price Per Acre", "Price Per AC")
        col_pplsf    = pick_column(cols, "Price Per Land SF")
        col_units    = pick_column(cols, "Number Of Units", "Number of Units", "Units")
        col_ppu      = pick_column(cols, "Price Per Unit")
        col_broker_c = pick_column(cols, "Listing Broker Company", "Sale Listing Broker Company")
        col_broker_n = pick_column(cols, "Listing Broker Contact", "Sale Listing Broker", "Listing Broker")
        col_broker_p = pick_column(cols, "Listing Broker Phone", "Sale Listing Broker Phone")
        col_broker_e = pick_column(cols, "Listing Broker Email", "Sale Listing Broker Email")
        col_class    = pick_column(cols, "Building Class", "Class")
        col_zoning   = pick_column(cols, "Zoning", "Zoning Code")
        col_market   = pick_column(cols, "Market", "Market Name")
        col_subm     = pick_column(cols, "Submarket Name", "Submarket")
        col_county   = pick_column(cols, "County", "County Name")

        warnings: list[str] = []
        if col_address is None:
            raise ValueError("CoStar parser: no Address column found")
        if col_status is None:
            warnings.append("No Sale Status column — defaulting to 'Active'")

        rows: list[ListingRow] = []
        for _, row in df.iterrows():
            raw = {c: row[c] for c in cols if c in row.index}
            # Strip pandas NaN out of raw_row so JSONB stays clean
            raw = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in raw.items()}

            address = to_str(row.get(col_address))
            if not address:
                continue  # skip blank-address rows

            sale_status = to_str(row.get(col_status)) if col_status else None
            sale_status = sale_status or "Active"

            rows.append(ListingRow(
                address=address,
                sale_status=sale_status,
                city=to_str(row.get(col_city)) if col_city else None,
                state=to_str(row.get(col_state)) if col_state else None,
                zip=to_str(row.get(col_zip)) if col_zip else None,
                sale_category=to_str(row.get(col_category)) if col_category else None,
                property_type=to_str(row.get(col_ptype)) if col_ptype else None,
                secondary_type=to_str(row.get(col_stype)) if col_stype else None,
                rating=to_int(row.get(col_rating)) if col_rating else None,
                size_sf=to_decimal(row.get(col_size)) if col_size else None,
                sale_price=to_decimal(row.get(col_price)) if col_price else None,
                price_per_sf=to_decimal(row.get(col_psf)) if col_psf else None,
                cap_rate=to_decimal(row.get(col_cap)) if col_cap else None,
                days_on_market=to_int(row.get(col_dom)) if col_dom else None,
                sale_type=to_str(row.get(col_stype2)) if col_stype2 else None,
                property_name=to_str(row.get(col_pname)) if col_pname else None,
                land_area_ac=to_decimal(row.get(col_land_ac)) if col_land_ac else None,
                land_area_sf=to_decimal(row.get(col_land_sf)) if col_land_sf else None,
                price_per_ac=to_decimal(row.get(col_ppac)) if col_ppac else None,
                price_per_land_sf=to_decimal(row.get(col_pplsf)) if col_pplsf else None,
                num_units=to_int(row.get(col_units)) if col_units else None,
                price_per_unit=to_decimal(row.get(col_ppu)) if col_ppu else None,
                listing_broker_company=to_str(row.get(col_broker_c)) if col_broker_c else None,
                listing_broker_contact=to_str(row.get(col_broker_n)) if col_broker_n else None,
                listing_broker_phone=to_str(row.get(col_broker_p)) if col_broker_p else None,
                listing_broker_email=to_str(row.get(col_broker_e)) if col_broker_e else None,
                building_class=to_str(row.get(col_class)) if col_class else None,
                zoning_listed=to_str(row.get(col_zoning)) if col_zoning else None,
                market=to_str(row.get(col_market)) if col_market else None,
                submarket=to_str(row.get(col_subm)) if col_subm else None,
                county=to_str(row.get(col_county)) if col_county else None,
                raw_row=raw,
            ))

        return ParseResult(rows=rows, detected_source="costar", warnings=warnings)


__all__ = ["Parser"]
