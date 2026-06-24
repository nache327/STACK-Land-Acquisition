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
        "codes": ["AR", "AR-IP", "R-1", "R-2", "OSRD", "OSRD-IP", "C-1", "C-1/SR", "C-2", "C-2/SR", "C-3", "C-3/SR", "C-4", "C-4/SR", "SI-1", "SI-1/SR", "SI-2", "SI-2/SR", "SI-3", "SI-3/SR", "SI-4"],
        "source_url": "https://maps.brentwoodtn.gov/arcgis/rest/services/Datasets/AdministrativeAreas/MapServer/9",
        "ordinance_url": "https://www.brentwoodtn.gov/Departments/Planning-and-Codes",
        "source_section": "Brentwood ArcGIS AdministrativeAreas/MapServer/9 (1,140 polygons, Zoning field) — full distinct list 21 codes queried 2026-06-23 post-Williamson adapter PR #359",
        "jurisdiction_note": "Brentwood TN — 21 distinct zone codes confirmed via live FeatureServer query (post-Agent 4 adapter PR #359). AR Agricultural/Res. Estate (31) + R-1 (61) + R-2 (373 dominant residential); OSRD Open Space Res (362) + OSRD-IP IP variant (56); C-1 Commercial Office through C-4 Town Center + /SR Special Review variants (10 commercial codes); SI-1 through SI-4 Service-Institutional + /SR variants (7 SI codes); AR-IP (1). Codes hyphenated (R-1 not R1) per live source — corrected from initial pre-stage. /SR suffix = Special Review overlay; IP suffix = Interchange/Industrial Park overlay.",
    },
    {
        "filename": "williamson_franklin.json",
        "muni": "Franklin",
        "codes": ["AG", "ER", "PD", "CI", "CC", "R1", "R2", "OR", "GO", "RC6", "LI", "RC12", "RC4", "MR", "R4", "R3", "NC", "HI", "R6", "1ST", "5TH", "DD"],
        "source_url": "https://publicmaps.franklintn.gov/arcgis/rest/services/Maps/ZoningWebMercator/MapServer/9",
        "ordinance_url": "https://www.franklintn.gov/government/departments-k-z/planning-and-sustainability/zoning-ordinance",
        "source_section": "Franklin publicmaps ZoningWebMercator/MapServer/9 (23,869 polygons, ZONECLASS field) — full distinct list 22 codes queried 2026-06-23 post-Williamson adapter PR #359",
        "jurisdiction_note": "Franklin TN — 22 distinct zone codes confirmed via live FeatureServer query (post-Agent 4 adapter PR #359). PD Planned District dominates (14,876 polygons, 62%); residential R1/R2/R3/R4/R6 + RC4/RC6/RC12 Residential Conditional series + MR Multi-Family + ER Estate Res (8 residential codes); commercial CC Central / NC Neighborhood / OR Office Res / GO General Office / 1ST + 5TH Districts (6 commercial); LI Light Industrial (337) + HI Heavy Industrial (60) — both flagged for verdict-truth queue (LI high permit probability, HI high permit probability for storage); CI Civic & Institutional (198); DD Downtown (112); AG Agriculture (31).",
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
    {
        "filename": "clackamas_lake_oswego.json",
        "muni": "Lake Oswego",
        "codes": ["CI", "CI/OC", "CR&D", "EC", "EC/R-0", "GC", "HC", "I", "IP", "MC", "NC", "NC/R-0", "OC", "OC/R-3", "PF", "PNA", "R-0", "R-10", "R-15", "R-2", "R-3", "R-5", "R-6", "R-7.5", "R-DD", "R-W", "WLG OC", "WLG R-2.5", "WLG RMU"],
        "source_url": "https://maps.ci.oswego.or.us/server/rest/services/Zoning_cache/MapServer/150",
        "ordinance_url": "https://www.ci.oswego.or.us/planning/zoning-information",
        "source_section": "City of Lake Oswego ArcGIS Zoning_cache/MapServer/150 (393 polygons, LAYER field) — full distinct list 29 codes queried 2026-06-23",
        "jurisdiction_note": "Lake Oswego OR (Multnomah/Clackamas) — 29 distinct zone codes confirmed via live FeatureServer query. WLG-prefixed codes are West Lake Grove neighborhood overlays. R-0/R-2/R-3/R-5/R-6/R-7.5/R-10/R-15/R-DD/R-W = residential; CI/CR&D/GC/HC/MC/NC/OC = commercial; EC = East End Commercial; I/IP = industrial; PF = Public Functions; PNA = Park & Natural Area. I/IP flagged for verdict-truth queue (industrial; high permit probability). Agent 11 verdict: VIABLE via city zoning (HALT on DLCD-as-zoning regional source).",
    },
    {
        "filename": "summit_park_city_corridor.json",
        "muni": "Summit County",
        "codes": ["RR", "RC", "TC", "CC", "NC", "HS", "MR", "SC", "AG-10", "AG-20", "AG-40", "AG-5", "AG-80", "C", "INDUS", "LI"],
        "source_url": "https://services2.arcgis.com/gyfpgFh2Wj2gglYD/arcgis/rest/services/Zoning_Service/FeatureServer",
        "ordinance_url": "https://www.summitcountyutah.gov/235/Planning-Division",
        "source_section": "Summit County ArcGIS Zoning_Service/FeatureServer layer 2 (Snyderville Basin Planning District, 34 polygons, Zone_Abbre field) + layer 3 (Eastern Summit Planning District, 44 polygons, Label field)",
        "jurisdiction_note": "Summit County UT (unincorporated Park City corridor — Promontory/Snyderville Basin/Eastern Summit). POLYGON CONFIRMATION REQUIRED at apply-time per Agent 11 Phase 6 outliers probe: Park City proper is already loaded/operational; substrate only useful if polygon is unincorporated Summit. Covers BOTH planning districts (16 codes): Snyderville Basin (RR/RC/TC/CC/NC/HS/MR/SC) + Eastern Summit (AG-10/AG-20/AG-40/AG-5/AG-80/C/INDUS/LI). INDUS/LI flagged for verdict-truth queue. If polygon = Park City proper, ABORT apply (use existing Park City matrix authoring instead).",
    },
    {
        "filename": "fairfield_westport.json",
        "muni": "Westport",
        "codes": ["A", "AA", "AAA", "B", "BCD", "BCD/H", "BCRR", "BPD", "CPD", "DDD2", "DDD3", "DDD4", "DOSRD 2", "DOSRD 3", "DOSRD1", "DOSRD3", "GBD", "GBD/S", "GBD/SM", "HDD", "HSD", "IHZ", "MHP", "MHZ", "OSRD", "PRD", "R-AHZ", "R-AHZ / W", "RBD", "RORD1", "RORD2", "RORD3", "RPOD", "R-RHOW", "SV"],
        "source_url": "https://services5.arcgis.com/lxjwLyi2Sx6yHvMJ/arcgis/rest/services/Zoning/FeatureServer/58",
        "ordinance_url": "https://online.encodeplus.com/regs/westport-ct/doc-viewer.aspx",
        "source_section": "Westport AxisGIS Zoning/FeatureServer/58 (127 polygons, ZONE_ field) — full distinct list 35 codes queried 2026-06-23 per Phase 2 NY/CT structural probe v2 PR #361",
        "jurisdiction_note": "Westport CT (Fairfield) — 35 distinct zone codes confirmed via live FeatureServer (Agent 9 Phase 2 probe v2). Residential A/AA/AAA + R-AHZ + R-RHOW; commercial GBD General Business + variants (GBD/S, GBD/SM, RBD Retail) + BCD/BCD/H Business Center; mixed-use DDD2/3/4 Designed Development + DOSRD Open Space Res Development variants + RORD1/2/3 Residential Overlay + RPOD Planned Overlay; special MHP/MHZ Manufactured Housing + HDD Historic + HSD Historic Setback + IHZ Inclusionary Housing + OSRD + PRD Planned Res + SV Special Village. CPD/BPD commercial/business planned districts. Overlays (APOZ/CAM Line/Open Space/IHZ/Village District) live on separate FeatureServer layers per probe note — substrate covers base zoning only; overlay handling deferred.",
    },
    {
        "filename": "fairfield_new_canaan.json",
        "muni": "New Canaan",
        "codes": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "O", "P", "Q"],
        "source_url": "https://hostingdata3.tighebond.com/arcgis/rest/services/NewCanaanCT/NewCanaanDynamic/MapServer/89",
        "ordinance_url": "https://www.ecode360.com/NE0075",
        "source_section": "New Canaan Tighe & Bond NewCanaanDynamic MapServer/89 (69 polygons; ZONING + Code fields) — 16 distinct Code values + 17 distinct (Code, ZONING) tuples queried 2026-06-23 per Phase 2 NY/CT structural probe v2 PR #361",
        "jurisdiction_note": "New Canaan CT (Fairfield) — 16 distinct zone Codes confirmed via live MapServer. Code is single-letter primary key; ZONING field maps to long name. Residential: A (1 Acre), B (1/2 Acre), C (1/3 Acre), D (2 Acre), E (4 Acre), F (A Residence), G (Apartment), H (B Residence); commercial: I (Business&Retail BA), J (BB+BD — note J maps to two distinct ZONING values), K (BC), L (RA), M (RB); multi-family/special: O (Multi-Family, 24 polygons dominant), P (Open Space, 9), Q (Waveny). Use Code as matrix municipality_key; verify both Code AND ZONING value at apply-time for J ambiguity.",
    },
    {
        "filename": "fairfield_wilton.json",
        "muni": "Wilton",
        "codes": ["CRA-10", "DE-10", "DE-5", "DRB", "DRD", "GB", "HOD", "R-1A", "R-2A", "SFAAHD", "THRD", "WC"],
        "source_url": "https://services1.arcgis.com/j6iFLXhyiD3XTMyD/arcgis/rest/services/CT_Wilton_Adv_Viewer_Layers/FeatureServer/13",
        "ordinance_url": "https://www.wiltonct.org/planning-zoning",
        "source_section": "Wilton CT QDSGIS CT_Wilton_Adv_Viewer_Layers/FeatureServer/13 (47 polygons, Description field) — full distinct list 12 codes queried 2026-06-23 per Phase 2 NY/CT structural probe v2 PR #361",
        "jurisdiction_note": "Wilton CT (Fairfield) — 12 distinct zone codes confirmed via live FeatureServer (zoning effective 10/29/2018 per layer name). Residential: R-1A (8) + R-2A + CRA-10 Cluster Res + SFAAHD Single-Family Active-Adult Housing + THRD Townhouse Res; commercial: GB General Business (11 dominant) + DE-5 + DE-10 Design Enterprise + WC Wilton Center + HOD Housing Opportunity Overlay; design: DRB Design Review Business + DRD Design Review Dist. Layer dated 2018 — may need amendment check at apply-time. OpenGov municipal parcel layer also carries embedded `zoning` field for crosswalk validation.",
    },
    {
        "filename": "arapahoe_englewood.json",
        "muni": "Englewood",
        "codes": ["I-1", "I-2", "M-1", "M-2", "MU-B-1", "MU-B-2", "MU-R-3-A", "MU-R-3-B", "MU-R-3-C", "PUD", "R-1-A", "R-1-B", "R-1-C", "R-2-A", "R-2-B"],
        "source_url": "https://agiso.englewoodco.gov/public/rest/services/LandUsePlanning/BaseZoningDistrictBoundaries/MapServer/0",
        "ordinance_url": "https://www.englewoodco.gov/government/city-departments/community-development/planning-zoning",
        "source_section": "Englewood CO ArcGIS BaseZoningDistrictBoundaries/MapServer/0 (94 polygons, NEWZONE field) — full distinct list 15 codes queried 2026-06-23 per Phase 6 secondary munis probe PR #360",
        "jurisdiction_note": "Englewood CO (Arapahoe; Phase 6 secondary rank 1 — VIABLE). 15 distinct codes confirmed via live MapServer. Residential R-1-A/B/C single-family + R-2-A/B two-family; mixed-use MU-B-1/B-2 Business + MU-R-3-A/B/C Res 3 variants; industrial I-1/I-2 + M-1/M-2 (4 codes flagged for verdict-truth queue — high permit probability); PUD Planned Unit Development (22 dominant). Companion parcel-zoning layer at agiso.englewoodco.gov ParcelsZoningNew/FeatureServer/0 carries 11,744 polygons with PIN/ADCITY/NEWZONE for direct join.",
    },
    {
        "filename": "arapahoe_greenwood_village.json",
        "muni": "Greenwood Village",
        "codes": ["A", "B-1", "B-1 PUD", "B-2", "B-2 PUD", "B-3", "B-3 PUD", "B-4", "B-4 PUD", "L-I", "M-C", "O-1", "O-2", "R-.05 PUD", "R-.1 PUD", "R-.25", "R-.25 PUD", "R-.5 PUD", "R-.75 PUD", "R-1.0", "R-1.0 PUD", "R-1.5 PUD", "R-2.0", "R-2.0 PUD", "R-2.5", "R-2.5 PUD", "T.C."],
        "source_url": "https://services.arcgis.com/LrtiPsdDQYj3b4gp/arcgis/rest/services/b16e6a436dc24550b521986d2a71f11a_public_view_1593194820169/FeatureServer/1",
        "ordinance_url": "https://greenwoodvillage.com/249/Zoning",
        "source_section": "Greenwood Village CO city-owned ArcGIS Urban service Zones layer 1 (6,024 polygons, CustomID field) — 27 distinct codes queried 2026-06-23 per Phase 6 secondary munis probe PR #360 (excludes 'Unknown' placeholder)",
        "jurisdiction_note": "Greenwood Village CO (Arapahoe; Phase 6 secondary rank 2 — PIVOT/authority QA pending). 27 distinct codes (excluding 'Unknown' placeholder). Residential R-.05/R-.1/R-.25/R-.5/R-.75/R-1.0/R-1.5/R-2.0/R-2.5 series with PUD variants (lot-size-based); commercial B-1/B-2/B-3/B-4 Business + PUD variants; office O-1/O-2; mixed M-C; light industrial L-I (1 polygon, flagged for verdict-truth queue); T.C. Town Center. Source caveat per probe: service is 'Urban planning-model' layer not plainly-named 'zoning districts' — authority confirmation needed before production backfill. PlanningMethod='zoning' + PlanningHorizon='existing' in sample rows suggests it IS the authoritative source.",
    },
    {
        "filename": "burlington_nj_medford.json",
        "muni": "Medford township",
        "codes": ["GD", "CC", "PD"],
        "source_url": "https://services8.arcgis.com/MkUfAWaYm2SQf4Qa/arcgis/rest/services/ME0295_ZoningDistricts_04282023/FeatureServer/0",
        "ordinance_url": "https://www.medfordtownship.com/189/Zoning",
        "source_section": "Medford ZoningHub ME0295_ZoningDistricts_04282023/FeatureServer/0 (94 polygons, Layer field) — 22 of 25 parcel-exposed codes already matrix-covered per Burlington NJ structural probe PR #369; 3 MISSING substrate-only",
        "jurisdiction_note": "HAND-OFF FOR NACHE — Medford Township Burlington NJ Phase 1 closer-out. Per probe: matrix has 22 rows / 22 distinct codes already human_reviewed; 3 parcel-exposed codes missing (GD 3,226 parcels / CC 158 / PD 30). Bergen catchall × 4 substrate-first holds for these 3 placeholders pending verdict-truth review. Verify district names at apply-time — placeholder names used (GD likely General Development; CC likely Community Commercial; PD likely Planned Development). NO existing matrix conflict expected since these codes are missing from current matrix per probe. Apply via _upload-matrix-rows replace_existing=False / factory_safe_write contract.",
    },
    {
        "filename": "burlington_nj_mount_laurel.json",
        "muni": "Mount Laurel township",
        "codes": ["B", "FR-MX", "I", "MCD", "MH-MF", "NC", "O-2", "O-3", "ORC", "R-1", "R-2", "R-3", "R-4", "R-8", "R1D", "SAAD", "SRI", "CHRC", "CSFA", "R3", "RAMW", "SGVE", "TARA"],
        "source_url": "https://map.govpilot.com/map/NJ/mountlaurel",
        "ordinance_url": "https://www.mountlaurelnj.gov/departments/planning_zoning",
        "source_section": "Mount Laurel Township NJ GovPilot public map (uid=6968, GMID=136, GCID=14) — layer code ZM Zoning Map; polygon API /api/v1/cmd/get/015 + parcel-detail API /api/v1/cmd/get/025S — 23 distinct codes union of polygon sample (17 codes) + parcel-detail sample (7 codes; I duplicate) per PR #369",
        "jurisdiction_note": "HAND-OFF FOR NACHE — Mount Laurel Township Burlington NJ Phase 1 (source + matrix blocked, source now viable via GovPilot anonymous public path). 18,518 prod parcels / 0 zoned currently. Existing matrix has only 1 row (I). 23 substrate placeholders covering BOTH GovPilot polygon zone names (B/FR-MX/I/MCD/MH-MF/NC/O-2/O-3/ORC/R-1/R-2/R-3/R-4/R-8/R1D/SAAD/SRI) AND parcel-detail ZONING values (CHRC/CSFA/R3/RAMW/SGVE/TARA — note R3 not R-3, parcel-detail may use different code spelling than polygons). I flagged for verdict-truth queue. Verify which code spelling Lane A's GovPilot adapter populates parcels.zoning_code with — may need apply-time consolidation if both sources active. Bergen catchall × 4 prohibited substrate-first per halt rule.",
    },
    {
        "filename": "burlington_nj_moorestown.json",
        "muni": "Moorestown township",
        "codes": ["AR-1", "L-MR", "LTC", "R-3-TH", "R1", "R1-Aa", "R1A", "R2", "R3", "RLC", "RLC-2", "SC-1", "SRC", "SRC-1", "SRC-2", "SRI"],
        "source_url": "https://map.govpilot.com/map/NJ/moorestown",
        "ordinance_url": "https://www.moorestown.nj.us/planning",
        "source_section": "Moorestown Township NJ GovPilot public map (uid=7555, GMID=139, GCID=14) — layer code ZM Zoning Map; polygon API /api/v1/cmd/get/015 — 16 distinct codes from polygon sample per PR #369 (parcel-detail ZONING blank 0/50, polygon source-of-record)",
        "jurisdiction_note": "HAND-OFF FOR NACHE — Moorestown Township Burlington NJ Phase 1 (source + matrix blocked, source now viable via GovPilot polygon backfill). 7,575 prod parcels / 0 zoned currently. Existing matrix has 4 rows (BP-1, BP-2, LTC, SRC) — LTC + SRC overlap with substrate codes and should be skipped by factory_safe_write (replace_existing=False); BP-1 + BP-2 may be legacy/unused. 16 substrate placeholders covering full polygon distinct list. Source vintage signal: Map_date 08/27/2008, LastUpdate 20140715-20090901 — preview gate must validate against current Moorestown ordinance before production write. RLC = Residential Low-Density Cluster; SRC = Suburban Res Cluster; LTC = Local Town Center (existing matrix names); verify all at apply-time. Bergen catchall × 4 prohibited substrate-first per halt rule.",
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
