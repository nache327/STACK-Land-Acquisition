"""Wilmington MA — Stage-4 FULL close (2026-07-08). Zero held cells. GI/HI/LI(=LI/O).

li=permitted GROUNDED (Table 1 §3.6.4 named by-right). ss/mw=prohibited GROUNDED
(§3.1 closed-list + Warehouse §3.6.1 reshipment-def + no SS use/overlay anywhere).
lgc=prohibited GROUNDED (ledger #58 reconcile: garage-condo=leased dead storage,
fits neither Light Industrial §3.6.4 nor Parking Facility §3.5.17 -> §3.1 prohibits).
Armed self-storage/garage-condo = 0. 269 parcels light-industrial-permitted (GI 198/
HI 67/LI 4). 2023 bylaw.
"""
WILMINGTON_ROWS = [{'zone_code': 'GI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]},
 {'zone_code': 'HI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]},
 {'zone_code': 'LI',
  'ss': 'prohibited',
  'mw': 'prohibited',
  'li': 'permitted',
  'lgc': 'prohibited',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': "§3.1: 'It is the intent of this Bylaw to prohibit in any district any use which "
                          "is not specifically permitted herein.' §3.6.1 Warehouse: '...where the principal "
                          'use of the warehouse facility is sorting materials, merchandise, products or '
                          "equipment for reshipment.' §3.6.4 Light Industrial: 'Warehouse and distribution; "
                          'assembly of finished products...printing or publishing plant; and other like '
                          "uses...' §3.5.17 Parking Facility: 'Commercial parking lot or parking garage.'",
                 'section': '§3.1/§3.6.1/§3.6.4/§3.5.17',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations + §3.1 / §3.5.17 / §3.6'}]}]
