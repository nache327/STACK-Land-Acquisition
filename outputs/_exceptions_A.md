# Session A exceptions — Middlesex MA (tier-2 batch, 2026-07-09)

## OPEN — needs Nache
| Muni | Item | What's needed |
|---|---|---|
| **Newton** | **No auto-fetchable CURRENT source.** Newton Chapter 30 Zoning is hosted only at `newtonma.gov/home/showpublisheddocument/72882/637634940612470000`, which is **Akamai-WAF-blocked**: `curl` (full browser UA + Accept/Referer headers) → HTTP "Access Denied"; WebFetch → 403; `web.archive.org` → no PDF snapshot (calendar HTML); Newton is **not on Municode or eCode360**. The only freely fetchable copy is `wabanareacouncil.com/.../Newton_zoning_clean_3-7-14.pdf` — but that is the **2014 DRAFT rezoning (never adopted)**, so grounding from it would be a Hudson-class staleness error (DO NOT use it). §4.4.1 is the use table; districts incl. Manufacturing "M" + Business + Mixed-Use. Newton is very wealthy (clears the HV/HHI gate easily) but has little industrial land — likely a modest-yield needle muni, not a no-op. | **Paste** the current Chapter 30 §4.4.1 Use Table (Newton's browser reaches Akamai fine) — specifically the self-storage / warehouse / manufacturing / motor-vehicle-storage rows across the M (Manufacturing), Business, and Mixed-Use districts, plus the legend + any "uses not listed are prohibited" clause. Then rebind (MAPC layer 2, muni='Newton') + ground. Source: newtonma.gov/home/showpublisheddocument/72882. |

## RESOLVED / GROUNDED this batch (tier-2 + Littleton carry-over)
| Muni | Result |
|---|---|
| Littleton | GROUNDED (eCode360 §173-26 auto-fetched via curl+UA print view). Needle: ss/mw conditional in I-A + I-B; li permitted I-A/I-B, conditional VC; lgc prohibited. |
| Burlington | GROUNDED. 0-NEEDLE correct no-op: §4.2.6.29 "Self-Storage Facility" = NO in ALL districts (deliberate amendment) + closed-list; li permitted IG/I/IR. No rebind (parcels already carry bylaw codes). |
| Holliston | GROUNDED (MAPC rebind from assessor codes). Needle: ss/mw conditional in Industrial (I) (warehouse/general-industrial-storage by-right → convention); li permitted I, conditional C1/VC; lgc prohibited. |
