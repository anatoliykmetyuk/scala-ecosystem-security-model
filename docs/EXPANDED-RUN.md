# Expanded pilot run: 2026-09-08

Snapshot: `20260908T063313771945Z`, generated from source commit `764998c`.
The local report is `output/preview.html`; the published destination is
https://anatoliikmt.me/scala-ecosystem-security-model/.

## Selection and actual universe

The selector examined all 76 Awesome Scala subsections, accepting the first ten
eligible projects in each and deduplicating repositories. It reused cached source
responses and fetched missing ones, including further entries needed for quotas.
Subsections with fewer eligible projects remain smaller. The resulting frozen
cohort contains **436 projects**, compared with the earlier saved-pool estimate of
392. Source URLs and ranks are retained in `config/seeds.yaml` and selection
request provenance in `config/selection-evidence.json`.

The matrix is JVM Scala 2.13 and 3. The twenty-artifact cap applies across both
binary versions combined, ranked by dependent-package counts. Publication checks
selected **3,254 project–artifact entries**, representing **3,251 distinct
coordinates**. Three duplicate ownership claims were reconciled using package
repository metadata; none remained unresolved. All dependency paths stay inside
the selected universe, to a maximum of five edges.

## Measurements

| Measurement | Result |
| --- | ---: |
| Frozen projects | 436 |
| Distinct selected coordinates | 3,251 |
| Starting latest-release artifact versions | 2,322 |
| Recorded version nodes | 4,864 |
| Successfully fetched version nodes | 4,578 |
| Recorded dependency edges | 14,077 |
| Verified project relationships | 2,370 |
| Known Value | 436 / 436 |
| Known Maintenance | 348 / 436 |
| Known Security | 219 / 436 |
| Collection time | 277.13 seconds (4 minutes 37 seconds) |
| Forward dependency collection | 176.02 seconds |
| Latest-release cache resolution | 0.10 seconds |
| Health collection/cache replay | 4.61 seconds |
| Analysis | 0.81 seconds |
| Render | 0.03 seconds |
| SQLite database | 20,443,136 bytes |
| Referenced compressed evidence | 182,270,177 bytes |
| Standalone preview | 1,181,757 bytes |

Collection timing excludes the earlier seed-selection step and subsequent review.
This is an explicit **cache-backed** run using `output/expanded-evidence`, merged
from preserved prior evidence and supplemented with missing requests. It is not a
fresh-crawl runtime prediction. Original source retrieval dates are retained.

Shortest retained path lengths: one hop 1,580; two hops 428; three hops 309;
four hops 45; five hops eight. Therefore **53 verified relationships require the
newly allowed fourth or fifth hop** within this expanded graph. This comparison
isolates path depth within the new graph, not the separate effects of changing
the cohort, Scala versions or artifact cap.

## Coverage and verification

The database records **753 gaps**: 590 fetch gaps, 59 artifact-ranking gaps,
42 release gaps, 34 declaration gaps, 25 version gaps and three reconciled
ownership records. Referenced requests: 11,047 HTTP 200, 578 HTTP 404 and 12 HTTP
202. Pending/missing source evidence remains unknown; no runtime or completeness
guarantee is inferred from the bounded coordinate universe.

Among candidates requiring metadata ranking, 1,289 have unknown dependent-package
counts; 149 such entries were selected using the documented unknown-last,
coordinate-name fallback. These are missing ranking inputs, not measured zeros.
Latest-release and Scala-matrix restrictions can leave a project without a usable
starting footprint. Failed version-API requests can still be supported by POM
evidence; only 25 version nodes failed both sources. Nodes merely recorded as
terminal dependencies are not all fetched, so unfetched-node counts are not
identical to failed resolutions.

Pipeline validation and additional database audits verified referential integrity,
twenty-artifact selection limits, ranking order, seed-only graph membership,
repository deduplication and the five-hop maximum. Automated validation passed
48 tests, Ruff and ty, including a regression that permits the fifth hop and
rejects the sixth. Browser verification covers the actual generated report,
collapsed formulas, search, dependency paths and responsive light/dark rendering.
Generated audits and screenshots are under `output/expanded-verification/` and
`output/expansion-estimate/`.

Publication verified: GitHub Actions deployment and validation passed for commit `327b9b3`. The live HTTPS HTML SHA-256 matches `site/index.html`: `936f3cbdb7595ded45aa8a8a483c69878b168b63b5aab1a1c1afab9608ba997e`.
