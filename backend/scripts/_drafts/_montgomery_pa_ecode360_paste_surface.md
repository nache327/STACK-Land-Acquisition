# Montgomery PA — eCode360-blocked munis: paste surface (Session D, 2026-07-09)

eCode360 hard-blocks automated fetch (403 on both WebFetch and the `/laws/LF*.pdf` source-PDF
path — verified 2026-07-09, same wall the 2026-06-29 recon hit). Town-PDF munis were auto-fetched
and shipped (Lansdale, Norristown, Souderton). The munis below have **no auto-fetchable authoritative
source**, so per the runbook ("an ordinance with no online source → paste") they are escalated for
Nache to grab the industrial + commercial **use tables** (permitted / conditional / special-exception
/ prohibited lists). On paste, Session D (or any session) applies verdicts the same way as the shipped
munis: closed-list check (catch #58), named-use defs, muni-scoped human_reviewed rows with verbatim
citations.

For each: grab the USE-REGULATION list of the INDUSTRIAL district(s) (the needle pool) + the main
COMMERCIAL districts (silence-prohibited coverage). What matters per district: (a) is self-storage /
self-service storage / mini-warehouse / "mini storage" NAMED? (b) is warehouse/warehousing/storage
by-right? → permitted (named) / conditional (warehouse-by-right, self-storage unnamed) / prohibited
(express NP or silence under a closed list).

## Hatboro Borough — Ch. 27 Zoning  (PRIORITY: biggest eCode360-only industrial pool)
Parcel industrial pool: **LI 86, HI 47, HI-MU 17** (= 150 parcels). Commercial: HB 20, O 46, RC-1/RC-2.
- Root: https://ecode360.com/31587171  · District classifications (Part 3): https://ecode360.com/31746991
- Grab: LI, HI, and HI-MU use lists (HI/HI-MU intent = "manufacturing, fabricating, processing plants
  with adjunctive office"); plus HB (Highway Business) + O (Office) for prohibited coverage.

## Pottstown Borough — Ch. 27 Zoning
Parcel pool needs decode: TTN 4439, NR 3467, D 200, DG 149, FO 122, GW 55, HM 48, GE 46, NB 41, HB 24, P 15.
(TTN/NR look form-based/residential; D/DG/GE likely commercial/downtown; the Keystone Opportunity Zone
industrial district is the needle — identify its code on paste.)
- Root: https://ecode360.com/14224071  · Districts (Part 3): https://ecode360.com/14224109
- Grab: the industrial district use list (KOZ / general industrial) + downtown/commercial (D, DG, GE) lists.

## Hatfield Township — Ch. 282 Zoning
Parcel industrial pool: **LI 404, IN 22**; business: BB 212, BA 197, B 157, C 273. (Big LI pool.)
- Root: https://ecode360.com/10506475  · LI Light Industrial (Art XX): https://ecode360.com/10507615
- Note (search preview): LI permitted uses include "Warehousing, including wholesale business" + "Truck
  terminal distribution center" + "Contractor's office and storage" → warehouse likely by-right →
  self-storage probably conditional (confirm self-storage not separately named). Grab the full LI Art XX
  use list + C / BB / BA business-district lists.

## Hatfield Borough — Ch. 27 Zoning
Parcel pool: R-1/2/3/4, CC 86, I 60, C 33, A 5. Needle = **I 60**.
- Root: https://ecode360.com/30847102  · Industrial (Part 18): https://ecode360.com/31212860
- Grab: the I Industrial use list + CC / C commercial lists.

## Bridgeport Borough — Ch. 560 Zoning  (⚠ version-mismatch flag)
Parcel pool: R2 1511, NC 358, R1 140, **LIC 50**, MUR 32, **GC 31**, R3 14, OS 7, TO 6, INS 4, **GIC 1**.
Needle = LIC (Light Industrial Commercial) + GC/GIC.
- eCode360 root: https://ecode360.com/10376944 (blocked)
- Town PDFs (all 403 to WebFetch — the CivicPlus `sites/g/files/vyhlif4176` path blocks automation):
  - revision info packet: https://www.bridgeportborough.org/sites/g/files/vyhlif4176/f/uploads/bridgeport_zoning_revision_info_packet.pdf
  - LIC amendment 2026-003: https://www.bridgeportborough.org/sites/g/files/vyhlif4176/f/uploads/2026-003_amending_chapter_560_lic_for_bc_ad_0.pdf
- ⚠ **Chapter 560 was REWRITTEN 11-11-2025 (Ord 2025-002) + amended 2026 (2026-003).** The parcel zone
  codes (LIC/GC/GIC/NC/MUR/TO) came from the county polygon layer and may predate the rewrite — verify
  the CURRENT Ch. 560 district codes match parcels.city='Bridgeport Borough' zoning_code before applying
  (catch: config-vs-current-bylaw, cf. Hudson MA MAPC-stale). Known: LIC allows multifamily/mixed-use as
  a conditional use (per 2026-003) — confirm self-storage treatment in LIC's use table on paste.
