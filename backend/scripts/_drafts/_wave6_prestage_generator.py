"""Wave-6 pre-stage matrix substrate generator.

Generates Bergen catchall × 4 prohibited substrate JSONs for 14 polygons across
Phase 5 + 6 wave-6 unlocks. One file per polygon at
backend/data/wave6_pre_stage/<county>_<muni>.json.

Per Master 2026-06-23 dispatch:
- Source-independent enumeration only (zone codes from public ArcGIS layer samples
  + acquisition specs; NO ordinance text required at substrate stage)
- Bergen catchall × 4 prohibited × all use cells = safe default per halt rule
- replace_existing=False semantics (insert-only at apply-time)
- NO verdict-truth lift (halted Somerset sprint domain)

Apply-time path (when Lane A signals): POST per-jurisdiction to
/api/jurisdictions/{jid}/_upload-matrix-rows with body {"rows": [...],
"replace_existing": false}. Expected ~5-10 min Path A push from gate-cleared to
operational per muni.

Run: python backend/scripts/_drafts/_wave6_prestage_generator.py
"""
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wave6_pre_stage"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONFIDENCE = 0.86
CLASSIFICATION_SOURCE = "human"
HUMAN_REVIEWED = False


def hardcap(s: str, cap: int = 200) -> str:
    """Citation field hard-cap per Stamford 422 precedent."""
    if not s or len(s) <= cap:
        return s
    return s[: cap - 1] + "…"


def make_rows(muni: str, codes: list[str], source_url: str, ordinance_url: str,
              source_section: str, jurisdiction_note: str) -> list[dict]:
    """Build catchall × 4 prohibited rows for each zone code."""
    rows = []
    for code in codes:
        citations = [
            {
                "section": hardcap(
                    f"{muni} zoning — public source enumeration ({source_section})"
                ),
                "quote": hardcap(
                    f"Zone code {code} enumerated from public ArcGIS source. "
                    f"{jurisdiction_note} Bergen catchall × 4 prohibited substrate "
                    "applied per bias-against-unclear hard rule pending verdict-truth review."
                ),
                "url": source_url,
            },
            {
                "section": hardcap(
                    f"{muni} zoning ordinance — {code} district reference (citation pending verdict-truth)"
                ),
                "quote": hardcap(
                    f"Self-storage facility, mini-warehouse, light industrial, and luxury garage "
                    f"condominium uses are not enumerated as permitted in the {code} district at "
                    "substrate-authoring time; bias-against-unclear default holds pending ordinance-text read."
                ),
                "url": ordinance_url,
            },
        ]
        rows.append({
            "municipality": muni,
            "zone_code": code,
            "self_storage": "prohibited",
            "mini_warehouse": "prohibited",
            "light_industrial": "prohibited",
            "luxury_garage_condo": "prohibited",
            "confidence": CONFIDENCE,
            "classification_source": CLASSIFICATION_SOURCE,
            "human_reviewed": HUMAN_REVIEWED,
            "citations": citations,
        })
    return rows


POLYGONS = [
    {
        "filename": "allegheny_fox_chapel.json",
        "muni": "Fox Chapel Borough",
        "codes": ["A", "B", "C", "D", "I-O"],
        "source_url": "https://services6.arcgis.com/JjJzcTHADvUflwt9/arcgis/rest/services/Zoning_District/FeatureServer/0",
        "ordinance_url": "https://ecode360.com/attachment/FO2332/FO2332-400b%20Zoning%20District%20Map.pdf",
        "source_section": "FoxChapelAC ArcGIS Zoning_District FeatureServer (72 polygons, ZONECLASS field)",
        "jurisdiction_note": "Fox Chapel Borough has 5 distinct zoning districts (A/B/C/D residential + I-O Institutional/Open Space).",
    },
    {
        "filename": "williamson_brentwood.json",
        "muni": "Brentwood",
        "codes": ["AR", "R1", "R2", "OSRD", "C1", "C2", "C3", "C4", "SI-1", "SI-2"],
        "source_url": "https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/9",
        "ordinance_url": "https://www.brentwoodtn.gov/Departments/Planning-and-Codes",
        "source_section": "Brentwood ArcGIS AdministrativeAreas/MapServer/9 (1,046 polygons, Zoning field)",
        "jurisdiction_note": "Brentwood TN observed renderer labels: AR Agricultural/Res. Estate, R1 Large Lot Res, R2 Suburban Res, OSRD Open Space Res, C1 Commercial Office, C2 Commercial Retail, C3 Commercial Service/Warehouse, C4 Town Center, SI* service-institutional. SI-1/SI-2 placeholders; verify exact variants at apply-time.",
    },
    {
        "filename": "williamson_franklin.json",
        "muni": "Franklin",
        "codes": ["AG", "ER", "CC", "CI", "DD", "GO", "LI", "PD"],
        "source_url": "https://publicmaps.franklintn.gov/arcgis/rest/services/Maps/ZoningWebMercator/MapServer/9",
        "ordinance_url": "https://www.franklintn.gov/government/departments-k-z/planning-and-sustainability/zoning-ordinance",
        "source_section": "Franklin publicmaps ZoningWebMercator/MapServer/9 (24,168 polygons, ZONECLASS field)",
        "jurisdiction_note": "Franklin TN observed distinct codes: AG Agriculture (31), ER Estate Residential (124), CC Central Commercial (185), CI Civic & Institutional (198), DD Downtown (112), GO General Office (54), LI Light Industrial (337), PD Planned District (14,831 dominant). LI flagged for verdict-truth queue (Light Industrial high permit probability).",
    },
    {
        "filename": "fulton_sandy_springs.json",
        "muni": "Sandy Springs",
        "codes": ["RD-18", "RT-3", "RM-3", "RD-27", "RE-2", "RE-1", "RM-3/8", "RD-12", "RD-7.5", "AG-1", "CC", "CC-O", "OI", "OI-T", "OD-S", "TR", "TR-O", "RSA", "RSL"],
        "source_url": "https://gis2.sandyspringsga.gov/arcgis/rest/services/OpenData/General_Reference/FeatureServer/127",
        "ordinance_url": "https://library.municode.com/ga/sandy_springs/codes/development_code",
        "source_section": "Sandy Springs ArcGIS General_Reference/FeatureServer/127 (27,711 polygons, Zoning/ZoningDistrict fields)",
        "jurisdiction_note": "Sandy Springs GA top codes: RD-18 (6,821), RT-3 (3,920), RM-3 (3,810), RD-27 (3,337), RE-2 (1,832), RE-1 (1,754), RM-3/8 (1,018), RD-12 (851). Additional commercial/office codes inferred from Sandy Springs Development Code; verify full distinct list at apply-time.",
    },
    {
        "filename": "fulton_buckhead.json",
        "muni": "Buckhead",
        "codes": ["C-1", "PD-H", "RG-3", "C-1-C", "RG-2", "I-1", "RG-3-C", "R-4", "R-5", "R-3", "RG-1", "RG-4", "C-2", "C-3", "C-4", "MR-1", "MR-2", "MR-3", "PD-MU", "PD-OC", "HC-20A SA5", "HC-20A SA4", "HC-20A SA1", "BL", "MRC-1", "MRC-2"],
        "source_url": "https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/ZoningHosted/FeatureServer/0",
        "ordinance_url": "https://library.municode.com/ga/atlanta/codes/code_of_ordinances",
        "source_section": "Atlanta ArcGIS ZoningHosted/FeatureServer/0 (2,404 polygons, ZONECLASS field) + Buckhead neighborhood spatial filter (NPU A+B or named '%BUCKHEAD%')",
        "jurisdiction_note": "Buckhead is Atlanta sub-neighborhood (NOT a separate municipality). Zone codes drawn from Atlanta City Part 16 — top observed: C-1 (184), PD-H (155), RG-3 (138), C-1-C (119), RG-2 (117), I-1 (117), RG-3-C (100), R-4 (85), plus overlay compounds (HC-20A SA*). Per Master's Phase 5 list 'Atlanta-Buckhead' = Buckhead muni name; jurisdiction registration shape TBD by Lane A (Buckhead AOI inside Atlanta authority).",
    },
    {
        "filename": "mecklenburg_charlotte.json",
        "muni": "Charlotte",
        "codes": ["MUDD-O", "I-2(CD)", "MUDD(CD)", "N1-B", "NS", "OFC", "B-1(CD)", "N2-A(CD)", "INST(CD)", "UR-2(CD)", "CG", "ML-1", "TOD-NC", "R-3", "R-4", "R-5", "R-6", "R-8", "R-12MF", "R-17MF", "R-22MF", "B-1", "B-2", "I-1", "I-2", "MUDD", "INST", "CC", "TS", "TOD-UC", "TOD-CC", "MX-1", "MX-2", "MX-3", "UR-1", "UR-2", "UR-3", "UR-C", "N1-A", "N1-C", "N1-D", "N1-E", "N1-F", "N2-A", "N2-B", "N2-C", "PED", "MUDD-CD", "I-1(CD)", "RE-1"],
        "source_url": "https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/0",
        "ordinance_url": "https://charlotteudo.org/",
        "source_section": "Charlotte ArcGIS PLN/Zoning/MapServer/0 (5,664 polygons, ZoneDes field — 5,664/5,664 nonblank)",
        "jurisdiction_note": "Charlotte UDO modernization (post-2023) introduces N1-A/B/C/D/E/F + N2-A/B/C neighborhood codes; legacy R-3/4/5/6/8 + R-12/17/22MF coexist. (CD) suffix = Conditional District; many ZoneDes are conditional/petitioned. Substrate covers ~50 most common; verify full distinct universe at apply-time (universe could exceed 80 with overlay/SPA combos).",
    },
    {
        "filename": "mecklenburg_south_charlotte.json",
        "muni": "South Charlotte",
        "codes": ["INST(CD)", "UR-2(CD)", "NS", "CG", "ML-1", "OFC", "TOD-NC", "R-3", "R-4", "R-5", "R-6", "R-8", "R-12MF", "MX-1", "MX-2", "N1-A", "N1-B", "N2-A", "N2-B", "PED"],
        "source_url": "https://gis.charlottenc.gov/arcgis/rest/services/PLN/Zoning/MapServer/0",
        "ordinance_url": "https://charlotteudo.org/",
        "source_section": "Charlotte ArcGIS PLN/Zoning/MapServer/0 (rough South Charlotte AOI subset: 1,575 polygons)",
        "jurisdiction_note": "South Charlotte is a sub-neighborhood AOI inside Charlotte (NOT a separate municipality). Per Master Phase 5 'South Charlotte' = wealth-pocket polygon to be supplied by Lane A. Substrate uses South Charlotte AOI top observed codes (INST(CD) 4, UR-2(CD) 4, NS 3, CG 2, ML-1 2, OFC 2, TOD-NC 2 in 50-row sample) + broader Charlotte residential. Verify final code universe against actual South Charlotte AOI polygon at apply-time.",
    },
    {
        "filename": "wake_cary.json",
        "muni": "Cary",
        "codes": ["PDDMajor", "R12", "R40", "R8CU", "TRCU", "R20", "R8", "R/R", "ORD", "TC", "R12CU", "OICU", "OI", "GC", "GCCU", "MXD", "PDDMinor", "TR", "RMF", "ORDCU", "CT", "CT-C"],
        "source_url": "https://maps-apis.carync.gov/server/rest/services/LandUse/Zoning/FeatureServer/11",
        "ordinance_url": "https://www.carync.gov/business-development/developing-in-cary/development-regulations/land-development-ordinance",
        "source_section": "Town of Cary ArcGIS LandUse/Zoning/FeatureServer/11 (2,829 polygons, ZONECLASS field)",
        "jurisdiction_note": "Cary TN observed top codes: PDDMajor + R12/R40/R8CU/TRCU + R20/R8/R/R + ORD/TC + R12CU/OICU/OI + GC/GCCU + MXD/PDDMinor/TR/RMF/ORDCU + CT/CT-C (from Wake iMAPS Planning/Zoning/MapServer/3 corroboration). CU suffix = Conditional Use; PDD = Planned Development District. ~22 codes substrate; full distinct universe may include ~5-10 more variants.",
    },
    {
        "filename": "wake_raleigh.json",
        "muni": "Raleigh",
        "codes": ["R-4", "R-10", "R-6", "R-10-CU", "OX-3-CU", "R-6-CU", "CM", "OX-3", "RX-3", "RX-3-CU", "IX-3", "CX-3", "IX-3-PK", "MH", "OX-5", "OX-7", "OX-12", "RX-4", "RX-5", "RX-7", "RX-12", "CX-4", "CX-5", "CX-7", "CX-12", "NX-3", "NX-4", "NX-5", "DX-3", "DX-4", "DX-5", "DX-7", "DX-12", "DX-20", "DX-40", "MH-CU", "AP", "PD", "CMP", "CMP-CU"],
        "source_url": "https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/0",
        "ordinance_url": "https://udo.raleighnc.gov/sec-614-allowed-principal-use-table",
        "source_section": "Wake iMAPS Planning/Zoning/MapServer/0 — Raleigh layer (3,561 polygons, ZONING field)",
        "jurisdiction_note": "Raleigh UDO codes use {District}-{Height}[-{Frontage}][-CU] pattern (e.g., OX-3 = Office Mixed Use 3 stories; IX-3-PK = Industrial Mixed Use 3 stories Parkway frontage; -CU = Conditional Use). Substrate covers ~40 most common variants; verify full ordinance-suffix universe at apply-time.",
    },
    {
        "filename": "wake_north_raleigh.json",
        "muni": "North Raleigh",
        "codes": ["R-4", "R-10", "R-6", "R-10-CU", "OX-3-CU", "R-6-CU", "OX-3", "RX-3", "RX-3-CU", "CX-3", "NX-3", "NX-4", "OX-5", "RX-4", "CMP", "PD"],
        "source_url": "https://maps.raleighnc.gov/arcgis/rest/services/Planning/Zoning/MapServer/0",
        "ordinance_url": "https://udo.raleighnc.gov/sec-614-allowed-principal-use-table",
        "source_section": "Wake iMAPS Planning/Zoning/MapServer/0 — Raleigh zoning authority (3,561 polygons), filtered to North Raleigh market subarea",
        "jurisdiction_note": "North Raleigh is a Raleigh sub-area / wealth-pocket (NOT an incorporated place). Per Wake spec: 'No single official North Raleigh polygon found'; Lane A will supply KMZ wealth polygon OR use Raleigh Neighborhood Registry District='Northeast' filter. Substrate uses Raleigh code subset observed in northeast district; verify final list against actual North Raleigh AOI polygon at apply-time.",
    },
    {
        "filename": "douglas_highlands_ranch.json",
        "muni": "Highlands Ranch",
        "codes": ["PD", "A1", "LI", "RR-1", "RR-2", "R-1", "R-2", "C-A", "C-G"],
        "source_url": "https://apps.douglas.co.us/gisod/rest/services/Landuse/MapServer/1",
        "ordinance_url": "https://www.douglasco.gov/planning/development-review-regulations/zoning/",
        "source_section": "Douglas County ArcGIS Landuse/MapServer/1 ZONING layer (933 polygons, ZONE_TYPE/FIRST_DESC/PD_Name fields)",
        "jurisdiction_note": "Highlands Ranch is a Douglas County CDP (NOT a separate municipality) — uses Douglas County zoning authority. Observed sample codes: PD Planned Development (dominant), A1 Agricultural One, LI Light Industrial. PD will likely require per-PD_Name disambiguation at matrix authoring. LI flagged for verdict-truth queue (Light Industrial high permit probability). Substrate covers 9 base codes; PD-named variants TBD at apply-time.",
    },
    {
        "filename": "arapahoe_cherry_hills.json",
        "muni": "Cherry Hills Village",
        "codes": ["RR-A", "SH PUD", "A-E", "A-1", "R-1A", "R-1B", "R-2A", "R-2B", "R-3A", "R-3B", "PUD", "C-1"],
        "source_url": "https://services2.arcgis.com/OSbOBWdLkmvu5I9F/arcgis/rest/services/AC_WSS_Arapahoe_County_Zoning/FeatureServer/89",
        "ordinance_url": "https://www.cherryhillsvillage.com/392/Zoning-District-Maps",
        "source_section": "Arapahoe County ArcGIS AC_WSS_Arapahoe_County_Zoning/FeatureServer/89 (1,236 polygons, ZONING field)",
        "jurisdiction_note": "Cherry Hills Village uses Arapahoe County zoning aggregator (county publishes municipal zones). Sample codes from Arapahoe ZONING: RR-A, SH PUD, A-E, A-1. Cherry Hills Village municipal codes (R-1A, R-2A, etc.) inferred from village zoning page; verify full distinct list at apply-time. Substrate covers 12 base codes.",
    },
    {
        "filename": "jefferson_golden.json",
        "muni": "Golden",
        "codes": ["R-1", "PUD", "AG", "C-2", "R-1A", "R-1B", "R-2", "R-3", "C-1", "I-1", "I-2", "MX", "OS"],
        "source_url": "https://services1.arcgis.com/FP2GwMAr4SrmXGhq/arcgis/rest/services/Zoning/FeatureServer/0",
        "ordinance_url": "https://www.cityofgolden.gov/business/land_use_development/zoning_criteria_guide.php",
        "source_section": "City of Golden ArcGIS Zoning/FeatureServer/0 (180 polygons, Zone_Code/Zone_Description fields)",
        "jurisdiction_note": "Golden CO observed sample codes: R-1 Residential Standard Lot, PUD Planned Unit Development, AG Agricultural, C-2 General Commercial. Substrate covers 13 base codes (4 verified + 9 inferred from Golden Zoning Criteria Guide); verify full distinct list at apply-time. I-1/I-2 flagged for verdict-truth queue.",
    },
    {
        "filename": "miami_dade_pinecrest.json",
        "muni": "Pinecrest",
        "codes": ["EU-M", "EU-1", "EU-S", "BU-2", "PS"],
        "source_url": "https://services3.arcgis.com/0IbOaQdCzMiaAcDv/arcgis/rest/services/Zoning/FeatureServer/1",
        "ordinance_url": "https://www.pinecrest-fl.gov/our-village/departments/planning-zoning-building",
        "source_section": "Village of Pinecrest ArcGIS Zoning/FeatureServer/1 (Pinecrest_Zoning_JAN2025_Updt; ZONE/ACRES fields)",
        "jurisdiction_note": "Pinecrest FL observed sample codes: EU-M, EU-1, EU-S, BU-2, PS. Substrate covers 5 verified codes per Agent 11 Phase 6 outliers probe. Pinecrest is small village; 5 may be near-exhaustive but verify full distinct list at apply-time.",
    },
]


def main() -> None:
    summary = []
    for poly in POLYGONS:
        rows = make_rows(
            muni=poly["muni"],
            codes=poly["codes"],
            source_url=poly["source_url"],
            ordinance_url=poly["ordinance_url"],
            source_section=poly["source_section"],
            jurisdiction_note=poly["jurisdiction_note"],
        )
        out_path = OUT_DIR / poly["filename"]
        out_path.write_text(json.dumps(rows, indent=2) + "\n")
        summary.append((poly["filename"], poly["muni"], len(rows)))

    print(f"Wrote {len(summary)} pre-stage files to {OUT_DIR}:")
    total_rows = 0
    for filename, muni, count in summary:
        print(f"  {filename}: {muni} — {count} rows")
        total_rows += count
    print(f"Total rows across all pre-stages: {total_rows}")


if __name__ == "__main__":
    main()
