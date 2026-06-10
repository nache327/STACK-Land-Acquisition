# Parcel-search latency baseline — 2026-06-09T22:33:45.349463+00:00

- API base: `https://capable-serenity-production-0d1a.up.railway.app`
- Jurisdictions measured: 66
- Trials per metric: 3
- Throttle: 0.25s between requests
- Timeout: 30.0s per request
- Bbox window: ±0.025° around jurisdiction centroid
- Sweep wall-clock: 2528.8s

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

Flagged: `cold_bbox_p50 > 4s` OR `cold_whole_p50 > 8s`. Candidates for Phase 3 follow-up — do not fix mid-flight. `parcel_count` and `payload_kb` are inlined so the parcel-count-vs-something-else question can be answered without re-running the harness.

- **Philadelphia, PA** (parcels=547,299, payload_kb=1886.1): cold_bbox=6.556s, cold_whole=8.891s
- **DuPage County, IL** (parcels=336,715, payload_kb=1979.3): cold_bbox=2.572s, cold_whole=8.143s
- **Hudson County, NJ** (parcels=143,305, payload_kb=1925.0): cold_bbox=2.566s, cold_whole=15.471s
- **Fairfax County, VA** (parcels=369,267, payload_kb=2077.0): cold_bbox=2.536s, cold_whole=8.578s
- **Montgomery County, MD** (parcels=281,249, payload_kb=2078.6): cold_bbox=2.486s, cold_whole=13.435s
- **Monmouth County, NJ** (parcels=251,486, payload_kb=1928.9): cold_bbox=2.415s, cold_whole=20.422s
- **Middlesex County, MA** (parcels=423,634, payload_kb=2166.7): cold_bbox=2.412s, cold_whole=13.729s
- **Nassau County, NY** (parcels=420,577, payload_kb=2405.9): cold_bbox=2.361s, cold_whole=20.823s
- **Bergen County, NJ** (parcels=281,646, payload_kb=1970.5): cold_bbox=2.306s, cold_whole=23.219s
- **Westchester County, NY** (parcels=257,914, payload_kb=1151.3): cold_bbox=2.127s, cold_whole=18.323s
- **Fairfield County, CT** (parcels=261,652, payload_kb=687.7): cold_bbox=1.977s, cold_whole=8.99s
- **Loudoun County, VA** (parcels=132,428, payload_kb=227.3): cold_bbox=1.859s, cold_whole=16.752s
