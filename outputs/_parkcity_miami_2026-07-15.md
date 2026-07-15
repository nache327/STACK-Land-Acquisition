# Park City corridor + Miami/Pinecrest (Phase 6) — triage outcome (2026-07-15)

**All 3 CLEAR the wealth gate (resort/ultra-affluent), but NONE has in-ring industrial → correct no-ops.**
Distinct from Pittsburgh/Minneapolis (which failed the ring-HV gate): here the binding constraint is the
**absence of self-storage-appropriate (industrial/service-commercial) zoning INSIDE the wealth ring** — the
industrial that exists sits outside the wealthy ring (Hudson lesson) or doesn't exist at all. Triage-first:
0 grounding, 0 binds. NEEDLE gate = dt10 HV≥475k & HHI≥100k, acres≥1.5. No re-score/CoStar.

## Threshold + zoning data
| City | jid | ring HVmax | gate pass | in-ring industrial | in-ring commercial | result |
|---|---|---|---|---|---|---|
| **Park City UT** | 13b01b39 | **$1,572,800** | 5,082 / 6,651 | **NONE** (ski resort — no industrial zone) | Comm 15 / CT 21 / RCom 1 | correct NO-OP |
| **Snyderville UT** | 72492dd8 | **$1,572,800** | 7,769 / 22,225 | **0 in-ring** (INDUS/LI/SC exist but 100% OUT-of-ring) | TC 21 / CC 3 / NC 3 | correct NO-OP |
| **Pinecrest FL** | 55da99fa | **$1,638,912** | 5,687 / 5,687 | **NONE** (affluent residential village) | BU-1A 14 / BU-2 5 / BU-1 4 | correct NO-OP |

## Detail
- **Park City** — clears gate strongly ($1.57M). It's a ski-resort town with **no industrial zone at all**;
  in-ring non-residential is resort-commercial (Comm/CT/RCom). Self-storage is not a resort-commercial use.
- **Snyderville/Promontory** — clears gate. The "genuine commercial/light-industrial" (Kimball Junction) IS
  real — **INDUS (7), LI (9), SC=Service-Commercial/light-industrial (131), C (67)** — but **every one has
  0 in-ring parcels at ANY lot size** (verified): the employment area sits entirely outside the $475k
  wealthy-residential ring (textbook Hudson lesson). In-ring wealth is RR/AG/HS/MR residential + **TC Town
  Center (21)** mixed-use resort core. Self-storage's home zone (SC) is out-of-ring.
- **Pinecrest** — clears gate strongly ($1.64M, 100% pass), but it's an affluent residential village (EU/RU
  estate/residential) that incorporated to restrict commercial; **no industrial zone**; in-ring = BU-1/BU-1A/
  BU-2 business (~23). Near-no-op exactly as flagged (South Charlotte pattern).

## Residual (flagged, NOT grounded — did not guess a verdict, #37)
The in-ring resort/town-center/village COMMERCIAL — **Snyderville TC (21), Park City Comm (15), Pinecrest
BU-1A/BU-2 (~19)** — was NOT ordinance-verified for a self-storage use. High prior it's prohibited (self-
storage is a service/industrial use these towns zone into their out-of-ring SC/industrial districts, and all
three actively restrict commercial). Summit County's code is on a CivicPlus DocumentCenter HTML viewer +
Municode-mirror (PDF not cleanly fetchable this session); Pinecrest LDC not fetched. If the coordinator wants
certainty on the ~55 in-ring commercial lots, a paste of the TC / Comm / BU-2 permitted-use lists would
confirm — but per the task's criterion (ground only where in-ring INDUSTRIAL clears), these are no-ops.

## Handoff to coordinator
- **Grounded needles: 0.** Park City / Snyderville / Pinecrest = correct no-ops. Unlike Pittsburgh/Minneapolis
  the gate CLEARS here ($1.5–1.6M ring HV) — the constraint is no in-ring industrial (self-storage zoning is
  absent or out-of-ring). Ring-precomputed all 3 (unblocks instantly if a commercial-zone paste reveals a
  self-storage use). No matrix writes; county jids untouched.
