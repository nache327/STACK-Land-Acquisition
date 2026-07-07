# Heuristic-Gate Enforcement — before/after drop list (read-only vs prod, 2026-07-07)

Attached per the 2.2 approval: eyeball the final drop by pocket. Fresh run at PR time.
Armed-pool invariant verified live: 48,110 human-reviewed + 11,122 llm/factory
lead-visible parcels — ZERO demoted. Delco's 65 armed (incl. 2026-07-07 verdicts) kept.

```
==============================================================================
HEURISTIC-VERDICT GATE � before/after (READ ONLY, no writes)
==============================================================================
Lead-visible parcels today (permitted/conditional): 765,905
  grounded (KEPT, human/llm/factory or human_reviewed): 102,235
  heuristic (WOULD BE DEMOTED to lead_eligible=false):  663,670
  demotion rate: 86.7%

Per-jurisdiction (sorted by # demoted):
jurisdiction                        before   gated    kept  %gated
------------------------------------------------------------------
Lake County, IL                    234,044 234,044       0    100%  <-- >50% LOSS
Middlesex County, MA                81,856  81,856       0    100%  <-- >50% LOSS
Montgomery County, PA               61,676  60,748     928     98%  <-- >50% LOSS
Salt Lake County, UT                46,027  46,027       0    100%  <-- >50% LOSS
Bucks County, PA                    46,166  45,970     196    100%  <-- >50% LOSS
Norfolk County, MA                  43,185  43,185       0    100%  <-- >50% LOSS
Chester County, PA                  36,910  36,645     265     99%  <-- >50% LOSS
South Jordan, UT                    14,541  14,541       0    100%  <-- >50% LOSS
Essex County, NJ                    12,117  12,117       0    100%  <-- >50% LOSS
Salt Lake City, UT                  11,753  11,753       0    100%  <-- >50% LOSS
Somerset County, NJ                 11,400   8,068   3,332     71%  <-- >50% LOSS
Saratoga Springs, UT                 7,352   7,352       0    100%  <-- >50% LOSS
West Jordan, UT                      6,781   6,781       0    100%  <-- >50% LOSS
Montgomery County, MD               16,037   5,853  10,184     36%
New York, NY                        32,703   4,306  28,397     13%
Provo, UT                            4,286   4,286       0    100%  <-- >50% LOSS
Orem, UT                             3,439   3,439       0    100%  <-- >50% LOSS
Ogden, UT                            3,021   3,021       0    100%  <-- >50% LOSS
Midvale, UT                          2,716   2,716       0    100%  <-- >50% LOSS
Howard County, MD                    4,548   2,571   1,977     57%  <-- >50% LOSS
West Valley City, UT                 2,495   2,495       0    100%  <-- >50% LOSS
Eagle Mountain, UT                   2,474   2,474       0    100%  <-- >50% LOSS
Hurricane, UT                        2,441   2,441       0    100%  <-- >50% LOSS
Sandy, UT                            2,368   2,368       0    100%  <-- >50% LOSS
Delaware County, PA                  2,780   2,255     525     81%  <-- >50% LOSS
Pleasant Grove, UT                   1,852   1,791      61     97%  <-- >50% LOSS
Murray, UT                           1,784   1,784       0    100%  <-- >50% LOSS
Tooele, UT                           1,589   1,589       0    100%  <-- >50% LOSS
Millcreek, UT                        1,267   1,267       0    100%  <-- >50% LOSS
Herriman, UT                         1,212   1,212       0    100%  <-- >50% LOSS
West Haven, UT                       1,190   1,190       0    100%  <-- >50% LOSS
Springville, UT                      1,069   1,069       0    100%  <-- >50% LOSS
Ivins, UT                              935     935       0    100%  <-- >50% LOSS
Fairfax County, VA                  15,717     827  14,890      5%
Roy, UT                                758     758       0    100%  <-- >50% LOSS
Lehi, UT                            12,189     669  11,520      5%
St. George, UT                       2,694     602   2,092     22%
Park City, UT                          555     555       0    100%  <-- >50% LOSS
North Salt Lake, UT                    526     526       0    100%  <-- >50% LOSS
Taylorsville, UT                       419     419       0    100%  <-- >50% LOSS
Kaysville, UT                          369     369       0    100%  <-- >50% LOSS
Bergen County, NJ                    4,575     257   4,318      6%
Cedar Hills, UT                        155     155       0    100%  <-- >50% LOSS
Holladay, UT                           109     109       0    100%  <-- >50% LOSS
Farmington, UT                         797     107     690     13%
Santa Clara, UT                         84      84       0    100%  <-- >50% LOSS
American Fork, UT                       57      57       0    100%  <-- >50% LOSS
Draper City, UT                        237      21     216      9%
Cottonwood Heights, UT                  73       4      69      5%
Westampton                               2       2       0    100%
Morris County, NJ                      490       0     490      0%
Highland, UT                           343       0     343      0%
Philadelphia, PA                     7,304       0   7,304      0%
Payson, UT                              10       0      10      0%
Monmouth County, NJ                  2,739       0   2,739      0%
Spanish Fork, UT                       720       0     720      0%
Loudoun County, VA                   4,941       0   4,941      0%
Allentown, PA                        3,430       0   3,430      0%
Burlington County, NJ                   18       0      18      0%
Westchester County, NY                 102       0     102      0%
Washington, UT                         418       0     418      0%
Hunterdon County, NJ                 1,782       0   1,782      0%
Lindon, UT                             278       0     278      0%

Breakdown by gate_reason x zone_class (demoted only):
jurisdiction                reason            zone_class       gated
--------------------------------------------------------------------
American Fork, UT           heuristic_source  industrial          57
Bergen County, NJ           low_confidence    industrial         240
Bergen County, NJ           low_confidence    mixed_use           16
Bergen County, NJ           low_confidence    commercial           1
Bucks County, PA            low_confidence    agricultural    22,874
Bucks County, PA            low_confidence    commercial       9,765
Bucks County, PA            low_confidence    residential      6,283
Bucks County, PA            low_confidence    industrial       5,083
Bucks County, PA            low_confidence    open_space       1,147
Bucks County, PA            low_confidence    mixed_use          810
Bucks County, PA            low_confidence    unknown              8
Cedar Hills, UT             heuristic_source  special             89
Cedar Hills, UT             heuristic_source  commercial          66
Chester County, PA          low_confidence    agricultural    17,628
Chester County, PA          low_confidence    commercial       9,483
Chester County, PA          low_confidence    industrial       4,156
Chester County, PA          low_confidence    mixed_use        2,513
Chester County, PA          low_confidence    residential      2,510
Chester County, PA          low_confidence    open_space         341
Chester County, PA          low_confidence    unknown             11
Chester County, PA          low_confidence    overlay              3
Cottonwood Heights, UT      low_confidence    agricultural         3
Cottonwood Heights, UT      low_confidence    mixed_use            1
Delaware County, PA         low_confidence    industrial       2,226
Delaware County, PA         low_confidence    open_space          29
Draper City, UT             heuristic_source  commercial          10
Draper City, UT             heuristic_source  industrial           6
Draper City, UT             heuristic_source  mixed_use            1
Draper City, UT             heuristic_source  agricultural         1
Draper City, UT             heuristic_source  open_space           1
Draper City, UT             heuristic_source  unknown              1
Draper City, UT             heuristic_source  residential          1
Eagle Mountain, UT          heuristic_source  residential      1,777
Eagle Mountain, UT          heuristic_source  special            384
Eagle Mountain, UT          heuristic_source  commercial         228
Eagle Mountain, UT          heuristic_source  industrial          55
Eagle Mountain, UT          heuristic_source  open_space          25
Eagle Mountain, UT          heuristic_source  unknown              5
Essex County, NJ            low_confidence    commercial       7,957
Essex County, NJ            low_confidence    mixed_use        2,861
Essex County, NJ            low_confidence    industrial       1,299
Fairfax County, VA          low_confidence    commercial         422
Fairfax County, VA          low_confidence    agricultural       364
Fairfax County, VA          low_confidence    industrial          41
Farmington, UT              low_confidence    agricultural        87
Farmington, UT              low_confidence    commercial          20
Herriman, UT                heuristic_source  unknown            891
Herriman, UT                heuristic_source  commercial         265
Herriman, UT                heuristic_source  industrial          39
Herriman, UT                heuristic_source  agricultural        12
Herriman, UT                heuristic_source  mixed_use            5
Holladay, UT                heuristic_source  commercial         109
Howard County, MD           low_confidence    mixed_use        1,393
Howard County, MD           low_confidence    commercial       1,156
Howard County, MD           low_confidence    industrial          22
Hurricane, UT               heuristic_source  industrial       1,844
Hurricane, UT               heuristic_source  commercial         564
Hurricane, UT               heuristic_source  special             33
Ivins, UT                   heuristic_source  commercial         935
Kaysville, UT               heuristic_source  commercial         274
Kaysville, UT               heuristic_source  industrial          95
Lake County, IL             low_confidence    industrial     231,360
Lake County, IL             low_confidence    agricultural     1,739
Lake County, IL             low_confidence    commercial         945
Lehi, UT                    heuristic_source  commercial         564
Lehi, UT                    heuristic_source  mixed_use          102
Lehi, UT                    heuristic_source  residential          2
Lehi, UT                    heuristic_source  overlay              1
Middlesex County, MA        low_confidence    commercial      32,253
Middlesex County, MA        low_confidence    agricultural    20,471
Middlesex County, MA        low_confidence    industrial      19,111
Middlesex County, MA        low_confidence    mixed_use       10,021
Midvale, UT                 heuristic_source  commercial       1,403
Midvale, UT                 heuristic_source  mixed_use          709
Midvale, UT                 heuristic_source  industrial         376
Midvale, UT                 heuristic_source  special            228
Millcreek, UT               heuristic_source  commercial       1,035
Millcreek, UT               heuristic_source  industrial         232
Montgomery County, MD       low_confidence    mixed_use        4,925
Montgomery County, MD       low_confidence    commercial         647
Montgomery County, MD       low_confidence    industrial         245
Montgomery County, MD       low_confidence    agricultural        36
Montgomery County, PA       low_confidence    residential     38,796
Montgomery County, PA       low_confidence    mixed_use        8,763
Montgomery County, PA       low_confidence    commercial       4,958
Montgomery County, PA       low_confidence    industrial       4,219
Montgomery County, PA       low_confidence    open_space       4,012
Murray, UT                  heuristic_source  industrial         907
Murray, UT                  heuristic_source  commercial         877
New York, NY                low_confidence    industrial       4,303
New York, NY                low_confidence    unknown              1
New York, NY                low_confidence    commercial           1
New York, NY                low_confidence    residential          1
Norfolk County, MA          low_confidence    commercial      32,428
Norfolk County, MA          low_confidence    agricultural     6,312
Norfolk County, MA          low_confidence    industrial       4,104
Norfolk County, MA          low_confidence    mixed_use          341
North Salt Lake, UT         heuristic_source  commercial         504
North Salt Lake, UT         heuristic_source  industrial          18
North Salt Lake, UT         heuristic_source  open_space           4
Ogden, UT                   heuristic_source  commercial       2,458
Ogden, UT                   heuristic_source  unknown            552
Ogden, UT                   heuristic_source  agricultural        11
Orem, UT                    heuristic_source  commercial       1,572
Orem, UT                    heuristic_source  special            882
Orem, UT                    heuristic_source  industrial         548
Orem, UT                    heuristic_source  unknown            433
Orem, UT                    heuristic_source  agricultural         4
Park City, UT               low_confidence    commercial         518
Park City, UT               low_confidence    industrial          37
Pleasant Grove, UT          heuristic_source  commercial       1,195
Pleasant Grove, UT          heuristic_source  unknown            240
Pleasant Grove, UT          heuristic_source  residential        219
Pleasant Grove, UT          heuristic_source  industrial         130
Pleasant Grove, UT          heuristic_source  mixed_use            7
Provo, UT                   heuristic_source  commercial       1,128
Provo, UT                   heuristic_source  mixed_use          877
Provo, UT                   heuristic_source  special            725
Provo, UT                   heuristic_source  open_space         702
Provo, UT                   heuristic_source  unknown            358
Provo, UT                   heuristic_source  industrial         234
Provo, UT                   heuristic_source  residential        215
Provo, UT                   heuristic_source  agricultural        47
Roy, UT                     heuristic_source  mixed_use          308
Roy, UT                     heuristic_source  commercial         293
Roy, UT                     heuristic_source  residential         71
Roy, UT                     heuristic_source  industrial          43
Roy, UT                     heuristic_source  unknown             43
Salt Lake City, UT          heuristic_source  mixed_use        9,207
Salt Lake City, UT          heuristic_source  industrial       2,469
Salt Lake City, UT          heuristic_source  commercial          77
Salt Lake County, UT        heuristic_source  special         18,683
Salt Lake County, UT        heuristic_source  mixed_use       10,753
Salt Lake County, UT        heuristic_source  commercial       7,913
Salt Lake County, UT        heuristic_source  industrial       6,173
Salt Lake County, UT        heuristic_source  unknown          2,272
Salt Lake County, UT        heuristic_source  agricultural       207
Salt Lake County, UT        heuristic_source  residential         20
Salt Lake County, UT        low_confidence    agricultural         3
Salt Lake County, UT        heuristic_source  open_space           2
Salt Lake County, UT        low_confidence    mixed_use            1
Sandy, UT                   heuristic_source  unknown          1,300
Sandy, UT                   heuristic_source  special          1,068
Santa Clara, UT             heuristic_source  special             36
Santa Clara, UT             heuristic_source  mixed_use           26
Santa Clara, UT             heuristic_source  commercial          13
Santa Clara, UT             heuristic_source  residential          9
Saratoga Springs, UT        heuristic_source  special          7,278
Saratoga Springs, UT        heuristic_source  industrial          40
Saratoga Springs, UT        heuristic_source  commercial          34
Somerset County, NJ         low_confidence    residential      4,024
Somerset County, NJ         low_confidence    agricultural     1,746
Somerset County, NJ         low_confidence    commercial       1,044
Somerset County, NJ         low_confidence    industrial         752
Somerset County, NJ         low_confidence    mixed_use          470
Somerset County, NJ         low_confidence    open_space          27
Somerset County, NJ         low_confidence    special              5
South Jordan, UT            heuristic_source  special         12,093
South Jordan, UT            heuristic_source  commercial       1,752
South Jordan, UT            heuristic_source  mixed_use          655
South Jordan, UT            heuristic_source  industrial          41
Springville, UT             heuristic_source  commercial         699
Springville, UT             heuristic_source  industrial         358
Springville, UT             heuristic_source  mixed_use           12
St. George, UT              heuristic_source  industrial         466
St. George, UT              heuristic_source  agricultural        69
St. George, UT              heuristic_source  unknown             52
St. George, UT              heuristic_source  special             11
St. George, UT              heuristic_source  commercial           4
Taylorsville, UT            heuristic_source  commercial         368
Taylorsville, UT            heuristic_source  residential         20
Taylorsville, UT            heuristic_source  special             14
Taylorsville, UT            heuristic_source  industrial          12
Taylorsville, UT            heuristic_source  unknown              5
Tooele, UT                  heuristic_source  commercial       1,049
Tooele, UT                  heuristic_source  mixed_use          288
Tooele, UT                  heuristic_source  industrial         252
West Haven, UT              heuristic_source  commercial         478
West Haven, UT              heuristic_source  unknown            472
West Haven, UT              heuristic_source  agricultural       240
West Jordan, UT             heuristic_source  special          5,194
West Jordan, UT             heuristic_source  industrial         724
West Jordan, UT             heuristic_source  commercial         668
West Jordan, UT             heuristic_source  agricultural       195
West Valley City, UT        heuristic_source  industrial       1,266
West Valley City, UT        heuristic_source  commercial       1,183
West Valley City, UT        heuristic_source  mixed_use           46
Westampton                  low_confidence    industrial           2
```
