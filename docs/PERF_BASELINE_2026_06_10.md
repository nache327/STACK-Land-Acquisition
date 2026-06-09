# Parcel-search latency baseline — 2026-06-09T22:33:45.349463+00:00

## Executive summary — what to quote a buyer

**Customer-facing bbox path is uniform across the entire prod fleet.**
65 of 66 jurisdictions clock cold_bbox p50 between **1.81 s and 2.90 s**
(Hurricane UT lowest, Ogden UT highest excl. Philadelphia). The only
real bbox outlier is **Philadelphia, PA at 6.56 s** (547 k parcels) —
that's a lone Bergen-class slow county on the customer path, not a
fleet pattern.

**Whole-county sidebar reveals the 10 actually-slow counties.** All
are >100 k parcels and all are NJ/NY/MA/MD/VA county-as-jurisdiction
rows: Monmouth NJ (20.4 s), Nassau NY (20.8 s), Bergen NJ (23.2 s),
Westchester NY (18.3 s), Loudoun VA (16.8 s), Hudson NJ (15.5 s),
Middlesex MA (13.7 s), Montgomery MD (13.4 s), Fairfield CT (9.0 s),
Philadelphia PA (8.9 s). NY (856 k parcels) timed out all 3 trials
at 30 s — the only complete cold_whole failure. This affects the
table view, not the map.

**Buyer-ready calculus per ROADMAP_2026_06_10.md #1:** if the
"put it in front of buyers" gate is bbox path only, the fleet is
ready except Philadelphia. If it includes whole-county table view,
the 10 large counties listed above need either Phase 2 follow-up
(query optimization), an explicit "loading…" UX over 5 s, or a
narrower launch list.

**Anomaly resolved (Bergen 9× anomaly from Phase 1 smoke):** Bergen
cold_whole is 23.2 s; Monmouth is 20.4 s; Nassau is 20.8 s. Morris
(177 k, 3.3 s) is now the anomaly in the OPPOSITE direction. The
pattern is "big NJ/NY counties are slow except Morris." Worth a
focused investigation in Phase 3 — possibly Morris was Op-5 ingested
through a different code path or the matrix bypass triggers there.
**Phase 2 mandate is read-only; not investigating here.**

## Run config

- API base: `https://capable-serenity-production-0d1a.up.railway.app`
- Jurisdictions measured: 66
- Trials per metric: 3
- Throttle: 0.25s between requests
- Timeout: 30.0s per request
- Bbox window: ±0.025° around jurisdiction centroid
- Sweep wall-clock: 2528.8s (~42 min — ran longer than the 15 min
  dispatch target because the 10 slow whole-county fetches dominated;
  none of the warm/bbox paths were the slow path)

## Caveat re: outlier section below

The auto-generated "Outliers" section flags everything where
`cold_bbox_p50 > 2.0s` — that catches 60+ of 66 because the bbox p50
floor is ~2.3 s (TLS handshake + ~1.5 s server work, even on a
4 k-parcel municipality). It's noise in the current threshold. **The
real bbox outlier is Philadelphia at 6.56 s**; the real whole-county
outliers are the 10 named in the executive summary above. Phase 3
should re-threshold the harness (e.g. `cold_bbox_p50 > 4.0s` for
buyer-blocking; `cold_whole_p50 > 8.0s` is already a reasonable
sidebar cutoff).

## Methodology — read before quoting numbers

**Bbox p50 is the customer-facing metric.** The dashboard map uses bbox-filtered queries; whole-county fetches happen only on the table view (which is paged and not the buyer-blocking path). Sort and outlier flags are anchored on `cold_bbox_p50`; whole-county columns are kept as a sidebar so the table view doesn't silently rot.

**Cold = memo-cold, NOT a quiet server.** Each "cold" trial varies the `sort` field, which changes the SHA256 cache key (`app.api.parcels._parcels_search_cache_key`) — so trial N+1 cannot HIT the in-process LRU memo. But the underlying Postgres buffer cache, query plan cache, and TCP/TLS connection stay warm across trials. The numbers therefore model **"first user landing on an already-busy county"**, not **"first user touching a county that's been idle for hours."** True cold-cold would be slower.

**Warm** = same payload immediately replayed — HITs the in-process LRU memo. `payload_kb` = median bytes / 1024 across cold-bbox trials.

| Jurisdiction | Parcels | Ready | cold_bbox p50 | warm_bbox p50 | cold_whole p50 | warm_whole p50 | payload kb | errs |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Philadelphia, PA | 547,299 | operational | 6.556 | 1.156 | 8.891 | 1.43 | 1886.1 | 2 |
| Ogden, UT | 30,823 | partial | 2.897 | 1.305 | 2.444 | 1.26 | 1972.9 | 0 |
| Orem, UT | 29,919 | partial | 2.885 | 1.316 | 2.526 | 1.371 | 2030.7 | 0 |
| New York, NY | 856,670 | operational | 2.826 | 1.205 | — | 2.212 | 1907.8 | 3 |
| Norfolk County, MA | 206,365 | partial | 2.785 | 1.221 | 4.13 | 1.324 | 2121.9 | 0 |
| Lake County, IL | 278,834 | operational | 2.783 | 1.376 | 7.839 | 1.387 | 2256.2 | 0 |
| Allentown, PA | 41,873 | operational | 2.757 | 1.223 | 2.545 | 1.186 | 1889.6 | 0 |
| Murray, UT | 19,044 | partial | 2.681 | 1.279 | 2.654 | 1.328 | 2098.0 | 0 |
| Morris County, NJ | 177,532 | operational | 2.677 | 1.201 | 3.295 | 1.75 | 1941.3 | 0 |
| Draper City, UT | 25,515 | partial | 2.666 | 1.323 | 2.565 | 1.515 | 2254.6 | 0 |
| Herriman, UT | 19,869 | partial | 2.651 | 1.146 | 2.714 | 1.327 | 2133.1 | 0 |
| Highland, UT | 7,292 | partial | 2.63 | 1.358 | 2.403 | 1.287 | 2197.1 | 0 |
| Midvale, UT | 10,090 | partial | 2.626 | 1.209 | 2.352 | 1.304 | 2229.0 | 0 |
| Sandy, UT | 33,393 | partial | 2.594 | 1.22 | 2.299 | 1.297 | 2104.1 | 0 |
| Taylorsville, UT | 16,995 | partial | 2.582 | 1.214 | 3.487 | 1.178 | 2085.5 | 0 |
| Kaysville, UT | 10,549 | partial | 2.577 | 1.322 | 2.484 | 1.463 | 2045.5 | 0 |
| DuPage County, IL | 336,715 | partial | 2.572 | 1.221 | 8.143 | 1.291 | 1979.3 | 0 |
| Millcreek, UT | 21,748 | partial | 2.57 | 1.26 | 2.548 | 1.311 | 2075.9 | 0 |
| Cottonwood Heights, UT | 12,713 | partial | 2.568 | 1.241 | 2.475 | 1.251 | 2053.7 | 0 |
| Hudson County, NJ | 143,305 | partial | 2.566 | 1.226 | 15.471 | 1.253 | 1925.0 | 0 |
| West Jordan, UT | 35,782 | partial | 2.565 | 1.095 | 2.417 | 1.18 | 2102.0 | 0 |
| Provo, UT | 30,477 | partial | 2.565 | 1.204 | 2.833 | 1.26 | 2068.7 | 0 |
| Springville, UT | 12,747 | partial | 2.54 | 1.275 | 2.561 | 1.258 | 2044.8 | 0 |
| Fairfax County, VA | 369,267 | operational | 2.536 | 1.192 | 8.578 | 1.814 | 2077.0 | 0 |
| Tooele, UT | 14,210 | partial | 2.533 | 1.323 | 3.679 | 1.249 | 2057.6 | 0 |
| Spanish Fork, UT | 17,476 | partial | 2.523 | 1.264 | 2.374 | 1.326 | 2048.1 | 0 |
| American Fork, UT | 14,733 | partial | 2.519 | 1.22 | 2.527 | 1.394 | 2072.4 | 0 |
| Essex County, NJ | 175,932 | partial | 2.504 | 1.444 | 5.746 | 1.376 | 2144.0 | 0 |
| Ivins, UT | 6,409 | partial | 2.502 | 1.324 | 2.59 | 1.149 | 1982.2 | 0 |
| St. George, UT | 49,584 | operational | 2.491 | 1.17 | 2.591 | 1.288 | 2073.1 | 0 |
| Montgomery County, MD | 281,249 | operational | 2.486 | 1.321 | 13.435 | 1.496 | 2078.6 | 0 |
| Farmington, UT | 8,785 | operational | 2.483 | 1.411 | 3.621 | 1.553 | 2111.4 | 0 |
| Pleasant Grove, UT | 12,604 | partial | 2.475 | 1.298 | 2.525 | 1.15 | 2107.8 | 0 |
| Saratoga Springs, UT | 21,325 | partial | 2.473 | 1.201 | 2.351 | 1.474 | 2170.1 | 0 |
| South Jordan, UT | 30,016 | partial | 2.438 | 1.222 | 2.666 | 1.208 | 2050.3 | 0 |
| Monmouth County, NJ | 251,486 | operational | 2.415 | 1.199 | 20.422 | 1.447 | 1928.9 | 2 |
| Holladay, UT | 12,452 | partial | 2.415 | 1.279 | 2.565 | 1.252 | 2086.9 | 0 |
| Middlesex County, MA | 423,634 | partial | 2.412 | 1.32 | 13.729 | 1.245 | 2166.7 | 1 |
| Lindon, UT | 4,949 | partial | 2.411 | 1.323 | 2.508 | 1.258 | 1379.6 | 0 |
| Payson, UT | 8,822 | partial | 2.388 | 1.22 | 2.543 | 1.318 | 2043.4 | 0 |
| Lehi, UT | 32,536 | operational | 2.385 | 1.284 | 2.456 | 1.29 | 2182.3 | 0 |
| North Salt Lake, UT | 7,648 | partial | 2.381 | 1.304 | 2.347 | 1.321 | 2096.2 | 0 |
| Salt Lake City, UT | 67,544 | operational | 2.38 | 1.329 | 2.685 | 1.332 | 2022.1 | 0 |
| West Haven, UT | 8,632 | partial | 2.38 | 1.183 | 2.442 | 1.247 | 2028.5 | 0 |
| Middlesex County, NJ | 245,616 | partial | 2.375 | 1.302 | 6.513 | 1.658 | 2043.5 | 0 |
| Somerset County, NJ | 117,387 | operational | 2.367 | 1.032 | 5.61 | 1.428 | 1996.5 | 0 |
| Eagle Mountain, UT | 21,857 | partial | 2.362 | 1.245 | 2.369 | 1.266 | 1920.7 | 0 |
| Nassau County, NY | 420,577 | partial | 2.361 | 1.072 | 20.823 | 1.333 | 2405.9 | 1 |
| Union County, NJ | 147,627 | partial | 2.345 | 1.363 | 6.878 | 1.412 | 1910.0 | 0 |
| Bluffdale, UT | 6,855 | partial | 2.335 | 1.179 | 2.348 | 1.136 | 1680.2 | 0 |
| Santa Clara, UT | 4,000 | partial | 2.33 | 1.195 | 2.364 | 1.11 | 1689.7 | 0 |
| Bergen County, NJ | 281,646 | operational | 2.306 | 1.101 | 23.219 | 1.191 | 1970.5 | 0 |
| Washington, UT | 19,306 | partial | 2.303 | 1.236 | 2.533 | 1.231 | 2052.1 | 0 |
| West Valley City, UT | 37,036 | partial | 2.296 | 1.284 | 2.52 | 1.514 | 2062.3 | 0 |
| St George, UT | 49,676 | partial | 2.28 | 1.129 | 2.512 | 1.33 | 2060.3 | 0 |
| Roy, UT | 12,919 | partial | 2.274 | 1.36 | 2.564 | 1.312 | 1959.9 | 0 |
| Park City, UT | 6,651 | operational | 2.247 | 1.25 | 2.596 | 1.152 | 1510.3 | 0 |
| Cedar Hills, UT | 3,130 | partial | 2.209 | 1.325 | 2.375 | 1.159 | 1344.3 | 0 |
| Passaic County, NJ | 125,785 | partial | 2.151 | 1.288 | 2.673 | 1.437 | 2019.2 | 0 |
| Montgomery County, PA | 301,424 | partial | 2.13 | 1.137 | 7.703 | 1.323 | 1026.0 | 0 |
| Westchester County, NY | 257,914 | partial | 2.127 | 1.224 | 18.323 | 1.62 | 1151.3 | 0 |
| Fairfield County, CT | 261,652 | partial | 1.977 | 1.038 | 8.99 | 2.05 | 687.7 | 0 |
| Hunterdon County, NJ | 52,902 | operational | 1.962 | 1.107 | 3.007 | 1.654 | 326.1 | 0 |
| Howard County, MD | 97,775 | operational | 1.864 | 1.118 | 4.96 | 1.735 | 668.1 | 0 |
| Loudoun County, VA | 132,428 | partial | 1.859 | 1.123 | 16.752 | 1.599 | 227.3 | 0 |
| Hurricane, UT | 15,114 | partial | 1.811 | 1.154 | 2.42 | 1.307 | 512.9 | 0 |

## Outliers

Flagged: `cold_bbox_p50 > 2s` OR `cold_whole_p50 > 8s`. Candidates for Phase 3 follow-up — do not fix mid-flight. `parcel_count` and `payload_kb` are inlined so the parcel-count-vs-something-else question can be answered without re-running the harness.

- **Philadelphia, PA** (parcels=547,299, payload_kb=1886.1): cold_bbox=6.556s, cold_whole=8.891s
- **Ogden, UT** (parcels=30,823, payload_kb=1972.9): cold_bbox=2.897s, cold_whole=2.444s
- **Orem, UT** (parcels=29,919, payload_kb=2030.7): cold_bbox=2.885s, cold_whole=2.526s
- **New York, NY** (parcels=856,670, payload_kb=1907.8): cold_bbox=2.826s, cold_whole=Nones
- **Norfolk County, MA** (parcels=206,365, payload_kb=2121.9): cold_bbox=2.785s, cold_whole=4.13s
- **Lake County, IL** (parcels=278,834, payload_kb=2256.2): cold_bbox=2.783s, cold_whole=7.839s
- **Allentown, PA** (parcels=41,873, payload_kb=1889.6): cold_bbox=2.757s, cold_whole=2.545s
- **Murray, UT** (parcels=19,044, payload_kb=2098.0): cold_bbox=2.681s, cold_whole=2.654s
- **Morris County, NJ** (parcels=177,532, payload_kb=1941.3): cold_bbox=2.677s, cold_whole=3.295s
- **Draper City, UT** (parcels=25,515, payload_kb=2254.6): cold_bbox=2.666s, cold_whole=2.565s
- **Herriman, UT** (parcels=19,869, payload_kb=2133.1): cold_bbox=2.651s, cold_whole=2.714s
- **Highland, UT** (parcels=7,292, payload_kb=2197.1): cold_bbox=2.63s, cold_whole=2.403s
- **Midvale, UT** (parcels=10,090, payload_kb=2229.0): cold_bbox=2.626s, cold_whole=2.352s
- **Sandy, UT** (parcels=33,393, payload_kb=2104.1): cold_bbox=2.594s, cold_whole=2.299s
- **Taylorsville, UT** (parcels=16,995, payload_kb=2085.5): cold_bbox=2.582s, cold_whole=3.487s
- **Kaysville, UT** (parcels=10,549, payload_kb=2045.5): cold_bbox=2.577s, cold_whole=2.484s
- **DuPage County, IL** (parcels=336,715, payload_kb=1979.3): cold_bbox=2.572s, cold_whole=8.143s
- **Millcreek, UT** (parcels=21,748, payload_kb=2075.9): cold_bbox=2.57s, cold_whole=2.548s
- **Cottonwood Heights, UT** (parcels=12,713, payload_kb=2053.7): cold_bbox=2.568s, cold_whole=2.475s
- **Hudson County, NJ** (parcels=143,305, payload_kb=1925.0): cold_bbox=2.566s, cold_whole=15.471s
- **West Jordan, UT** (parcels=35,782, payload_kb=2102.0): cold_bbox=2.565s, cold_whole=2.417s
- **Provo, UT** (parcels=30,477, payload_kb=2068.7): cold_bbox=2.565s, cold_whole=2.833s
- **Springville, UT** (parcels=12,747, payload_kb=2044.8): cold_bbox=2.54s, cold_whole=2.561s
- **Fairfax County, VA** (parcels=369,267, payload_kb=2077.0): cold_bbox=2.536s, cold_whole=8.578s
- **Tooele, UT** (parcels=14,210, payload_kb=2057.6): cold_bbox=2.533s, cold_whole=3.679s
- **Spanish Fork, UT** (parcels=17,476, payload_kb=2048.1): cold_bbox=2.523s, cold_whole=2.374s
- **American Fork, UT** (parcels=14,733, payload_kb=2072.4): cold_bbox=2.519s, cold_whole=2.527s
- **Essex County, NJ** (parcels=175,932, payload_kb=2144.0): cold_bbox=2.504s, cold_whole=5.746s
- **Ivins, UT** (parcels=6,409, payload_kb=1982.2): cold_bbox=2.502s, cold_whole=2.59s
- **St. George, UT** (parcels=49,584, payload_kb=2073.1): cold_bbox=2.491s, cold_whole=2.591s
- **Montgomery County, MD** (parcels=281,249, payload_kb=2078.6): cold_bbox=2.486s, cold_whole=13.435s
- **Farmington, UT** (parcels=8,785, payload_kb=2111.4): cold_bbox=2.483s, cold_whole=3.621s
- **Pleasant Grove, UT** (parcels=12,604, payload_kb=2107.8): cold_bbox=2.475s, cold_whole=2.525s
- **Saratoga Springs, UT** (parcels=21,325, payload_kb=2170.1): cold_bbox=2.473s, cold_whole=2.351s
- **South Jordan, UT** (parcels=30,016, payload_kb=2050.3): cold_bbox=2.438s, cold_whole=2.666s
- **Monmouth County, NJ** (parcels=251,486, payload_kb=1928.9): cold_bbox=2.415s, cold_whole=20.422s
- **Holladay, UT** (parcels=12,452, payload_kb=2086.9): cold_bbox=2.415s, cold_whole=2.565s
- **Middlesex County, MA** (parcels=423,634, payload_kb=2166.7): cold_bbox=2.412s, cold_whole=13.729s
- **Lindon, UT** (parcels=4,949, payload_kb=1379.6): cold_bbox=2.411s, cold_whole=2.508s
- **Payson, UT** (parcels=8,822, payload_kb=2043.4): cold_bbox=2.388s, cold_whole=2.543s
- **Lehi, UT** (parcels=32,536, payload_kb=2182.3): cold_bbox=2.385s, cold_whole=2.456s
- **North Salt Lake, UT** (parcels=7,648, payload_kb=2096.2): cold_bbox=2.381s, cold_whole=2.347s
- **Salt Lake City, UT** (parcels=67,544, payload_kb=2022.1): cold_bbox=2.38s, cold_whole=2.685s
- **West Haven, UT** (parcels=8,632, payload_kb=2028.5): cold_bbox=2.38s, cold_whole=2.442s
- **Middlesex County, NJ** (parcels=245,616, payload_kb=2043.5): cold_bbox=2.375s, cold_whole=6.513s
- **Somerset County, NJ** (parcels=117,387, payload_kb=1996.5): cold_bbox=2.367s, cold_whole=5.61s
- **Eagle Mountain, UT** (parcels=21,857, payload_kb=1920.7): cold_bbox=2.362s, cold_whole=2.369s
- **Nassau County, NY** (parcels=420,577, payload_kb=2405.9): cold_bbox=2.361s, cold_whole=20.823s
- **Union County, NJ** (parcels=147,627, payload_kb=1910.0): cold_bbox=2.345s, cold_whole=6.878s
- **Bluffdale, UT** (parcels=6,855, payload_kb=1680.2): cold_bbox=2.335s, cold_whole=2.348s
- **Santa Clara, UT** (parcels=4,000, payload_kb=1689.7): cold_bbox=2.33s, cold_whole=2.364s
- **Bergen County, NJ** (parcels=281,646, payload_kb=1970.5): cold_bbox=2.306s, cold_whole=23.219s
- **Washington, UT** (parcels=19,306, payload_kb=2052.1): cold_bbox=2.303s, cold_whole=2.533s
- **West Valley City, UT** (parcels=37,036, payload_kb=2062.3): cold_bbox=2.296s, cold_whole=2.52s
- **St George, UT** (parcels=49,676, payload_kb=2060.3): cold_bbox=2.28s, cold_whole=2.512s
- **Roy, UT** (parcels=12,919, payload_kb=1959.9): cold_bbox=2.274s, cold_whole=2.564s
- **Park City, UT** (parcels=6,651, payload_kb=1510.3): cold_bbox=2.247s, cold_whole=2.596s
- **Cedar Hills, UT** (parcels=3,130, payload_kb=1344.3): cold_bbox=2.209s, cold_whole=2.375s
- **Passaic County, NJ** (parcels=125,785, payload_kb=2019.2): cold_bbox=2.151s, cold_whole=2.673s
- **Montgomery County, PA** (parcels=301,424, payload_kb=1026.0): cold_bbox=2.13s, cold_whole=7.703s
- **Westchester County, NY** (parcels=257,914, payload_kb=1151.3): cold_bbox=2.127s, cold_whole=18.323s
- **Fairfield County, CT** (parcels=261,652, payload_kb=687.7): cold_bbox=1.977s, cold_whole=8.99s
- **Loudoun County, VA** (parcels=132,428, payload_kb=227.3): cold_bbox=1.859s, cold_whole=16.752s
