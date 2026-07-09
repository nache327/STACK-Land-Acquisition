"""Wilmington MA — Stage-4 industrial split (2026-07-08). GI/HI/LI(=LI/O).

light_industrial GROUNDED permitted (Table 1 §3.6.4, by-right GI/HI/LI-O); lgc
conditional by inference. ss/mw HELD unclear this paste per directive. Both hold-
blockers RESOLVED post-write: (1) Warehouse §3.6.1 def = sorting-for-reshipment
distribution warehouse, NOT self-storage; (2) §3.1 closed-list ('prohibit any use
not specifically permitted herein'); (3) §6.7 + full-bylaw scan = NO self-storage
use/definition/overlay anywhere. => ss/mw flip-to-grounded-prohibited supported,
awaiting explicit go. 2023 bylaw, Table 1.
"""
WILMINGTON_ROWS = [{'zone_code': 'GI',
  'ss': 'unclear',
  'mw': 'unclear',
  'li': 'permitted',
  'lgc': 'conditional',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': '3.6.1 Warehouse: GI Yes HI Yes LI/O Yes | 3.6.2 Bulk Material Storage/Sales: GI '
                          'Yes HI Yes LI/O No | 3.6.3 Heavy Vehicular Dealer/Repair/Rental: GI SP HI SP LI/O '
                          'No | 3.6.4 Light Industrial: GI Yes HI Yes LI/O Yes | 3.6.5 Limited '
                          'Manufacturing: GI SP HI SP LI/O SP | 3.6.6 General Manufacturing: GI SP HI SP '
                          'LI/O No (header cols: R10 R20 R60 O55 NM NB GB CB GI HI LI/O; GI/HI/LI/O = last 3 '
                          'district columns).',
                 'section': 'Table 1 §3.6.1-3.6.6',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations §3.6 (Classification of Industrial Uses); legend Yes=by-right, '
                              'SP=special permit (Board of Appeals), No=prohibited; §3.1 closed-list: '
                              "'prohibit in any district any use which is not specifically permitted "
                              "herein'"}]},
 {'zone_code': 'HI',
  'ss': 'unclear',
  'mw': 'unclear',
  'li': 'permitted',
  'lgc': 'conditional',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': '3.6.1 Warehouse: GI Yes HI Yes LI/O Yes | 3.6.2 Bulk Material Storage/Sales: GI '
                          'Yes HI Yes LI/O No | 3.6.3 Heavy Vehicular Dealer/Repair/Rental: GI SP HI SP LI/O '
                          'No | 3.6.4 Light Industrial: GI Yes HI Yes LI/O Yes | 3.6.5 Limited '
                          'Manufacturing: GI SP HI SP LI/O SP | 3.6.6 General Manufacturing: GI SP HI SP '
                          'LI/O No (header cols: R10 R20 R60 O55 NM NB GB CB GI HI LI/O; GI/HI/LI/O = last 3 '
                          'district columns).',
                 'section': 'Table 1 §3.6.1-3.6.6',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations §3.6 (Classification of Industrial Uses); legend Yes=by-right, '
                              'SP=special permit (Board of Appeals), No=prohibited; §3.1 closed-list: '
                              "'prohibit in any district any use which is not specifically permitted "
                              "herein'"}]},
 {'zone_code': 'LI',
  'ss': 'unclear',
  'mw': 'unclear',
  'li': 'permitted',
  'lgc': 'conditional',
  'confidence': 0.95,
  'human_reviewed': True,
  'citations': [{'quote': '3.6.1 Warehouse: GI Yes HI Yes LI/O Yes | 3.6.2 Bulk Material Storage/Sales: GI '
                          'Yes HI Yes LI/O No | 3.6.3 Heavy Vehicular Dealer/Repair/Rental: GI SP HI SP LI/O '
                          'No | 3.6.4 Light Industrial: GI Yes HI Yes LI/O Yes | 3.6.5 Limited '
                          'Manufacturing: GI SP HI SP LI/O SP | 3.6.6 General Manufacturing: GI SP HI SP '
                          'LI/O No (header cols: R10 R20 R60 O55 NM NB GB CB GI HI LI/O; GI/HI/LI/O = last 3 '
                          'district columns).',
                 'section': 'Table 1 §3.6.1-3.6.6',
                 'ordinance': 'Town of Wilmington Zoning Bylaw, 2023 edition, Table 1 Principal Use '
                              'Regulations §3.6 (Classification of Industrial Uses); legend Yes=by-right, '
                              'SP=special permit (Board of Appeals), No=prohibited; §3.1 closed-list: '
                              "'prohibit in any district any use which is not specifically permitted "
                              "herein'"}]}]
