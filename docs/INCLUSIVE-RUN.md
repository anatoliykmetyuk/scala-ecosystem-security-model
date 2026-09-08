# Full coverage including ZIO and Mill: 2026-09-08

Snapshot: `20260908T072758329207Z`, source commit `afb6d56`.

## Scope

All 76 Awesome Scala subsections were traversed through their listing pages. The frozen seed contains 548 eligible repositories from 897 unique listed repositories. Eligibility requires Scala as the largest source language, a published coordinate in the configured matrix and latest-release evidence. Source ranks, categories and request provenance are retained in the seed and selection-evidence files. There is no per-subsection or overall project quota.

The matrix remains JVM Scala 2.13 and 3. Select at most 50 published coordinates per repository, ranked by dependent-package count, with unknown counts last and coordinate-name ties. The cap applies across both binary versions combined. All dependency paths stay inside this selected seed universe, with a maximum of five edges and actual intermediate versions.

## Measurements

| Measurement | Result |
| --- | ---: |
| Projects | 548 |
| Selected project–artifact entries | 5,685 |
| Distinct selected coordinates | 5,661 |
| Recorded version nodes | 8,256 |
| Edges | 26,258 |
| Verified project relationships | 3,648 |
| Recorded gaps | 1,362 |
| Referenced HTTP responses | 18,458 |
| New HTTP responses during rebuild | 1,484 |
| Collection seconds | 250.16 |
| SQLite bytes | 32,309,248 |
| Compressed referenced evidence bytes | 158,631,393 |
| Standalone HTML bytes | 1,578,145 |

Collection timing measures cache replay plus missing HTTP requests. It excludes seed selection, validation and publication. Existing response timestamps and cached failures remain preserved. This is not a fresh-crawl runtime estimate.

## Coverage

- maintenance known: 439 / 548.
- security known: 263 / 548.
- value known: 547 / 548.

Gaps by stage: artifact_selection 28, declaration 214, fetch 1017, ownership 24, release 46, version 33.

HTTP statuses: 200: 17441, 202: 15, 404: 947, 522: 55.

Verified paths by hop count: 1: 2302, 2: 725, 3: 481, 4: 106, 5: 34.

Cached failures remain visible, including 55 upstream HTTP 522 responses from the previous collection. Missing or pending evidence does not establish verified relationships or healthy scores. Exposure remains restricted to the frozen seed.

## Incremental inclusion and verification

The previous 529-project run finished and passed data and browser validation before removing the repository-specific exclusions. The new selection retained every previous project and added 19 eligible repositories. The fifty-artifact cap and all other collection rules remain unchanged.

The follow-up reused `output/expanded-evidence`, replaying existing responses without refreshing them and fetching missing URLs needed by the expanded graph. It recalculated paths and scores for the combined universe, including relationships from existing projects to newly admitted targets. It took 4 minutes 10 seconds, compared with 15 minutes 25 seconds for the preceding full-list expansion. Historical snapshots remain available.

All 49 tests, Ruff lint/format checks and ty checks passed, as did GitHub Actions validation. Database audits verified ranking order, fifty-artifact caps, five-hop paths, closed-universe boundaries and foreign keys. Browser verification passed for all 548 cards, mathematical formula disclosures, path expand/collapse, search, repository links and responsive light/dark layouts.
