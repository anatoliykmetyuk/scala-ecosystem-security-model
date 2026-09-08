# Full Awesome Scala run: 2026-09-08

Snapshot: `20260908T071025506276Z`, source commit `7bfd0d9`.

## Scope

All 76 Awesome Scala subsections were traversed through their listing pages. The frozen seed contains 529 eligible repositories from 897 unique listed repositories. Eligibility requires Scala as the largest source language, a published coordinate in the configured matrix and latest-release evidence. Source ranks, categories and request provenance are retained in the seed and selection-evidence files. There is no per-subsection or overall project quota.

The matrix remains JVM Scala 2.13 and 3. Select at most 50 published coordinates per repository, ranked by dependent-package count, with unknown counts last and coordinate-name ties. The cap applies across both binary versions combined. All dependency paths stay inside this selected seed universe, with a maximum of five edges and actual intermediate versions.

## Measurements

| Measurement | Result |
| --- | ---: |
| Projects | 529 |
| Selected project–artifact entries | 5,369 |
| Distinct selected coordinates | 5,348 |
| Starting latest-release versions | 3,634 |
| Recorded version nodes | 7,457 |
| Edges | 23,738 |
| Verified project relationships | 3,266 |
| Recorded gaps | 1,308 |
| Referenced HTTP responses | 16,901 |
| Collection seconds | 924.67 |
| SQLite bytes | 29,380,608 |
| Compressed referenced evidence bytes | 100,551,824 |
| Standalone HTML bytes | 1,487,222 |

Collection timing measures cache replay plus missing HTTP requests. It excludes seed selection, validation and publication. Existing response timestamps and cached failures remain preserved. This is not a fresh-crawl runtime estimate.

## Coverage

- maintenance known: 426 / 529.
- security known: 254 / 529.
- value known: 528 / 529.

Gaps by stage: artifact_selection 26, declaration 214, fetch 969, ownership 21, release 45, version 33.

HTTP response statuses: 200: 15932, 202: 13, 404: 901, 522: 55.

Verified paths by hop count: 1: 2154, 2: 605, 3: 416, 4: 79, 5: 12.

Missing or pending evidence does not establish verified relationships or healthy scores. Artifact-ranking inputs can remain unknown; those coordinates sort after known counts. The reported exposure is restricted to the frozen seed, not the whole Maven ecosystem.

## Verification

All 49 tests, Ruff lint/format checks and ty type checking passed. The collected database passed graph, score and foreign-key validation, plus checks of artifact caps, ranking order, five-hop paths and closed-universe boundaries.

Browser verification passed for all 529 cards, collapsed mathematical formulas, beneficiary paths, search, repository links and light/dark mobile/desktop layouts. This validated checkpoint is retained locally; publication will include the subsequently authorized ZIO/Mill additions.
