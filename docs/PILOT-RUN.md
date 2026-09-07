# Verified pilot run: 2026-09-07

The current pilot was collected, validated and rendered. Open `output/preview.html` locally. The final snapshot is `output/runs/20260907T133955659058Z/snapshot.sqlite`; the current database path is also recorded in `output/latest-database.txt`. Generated artifacts remain ignored by Git.

## Scope and provenance

279 frozen Scala seed projects; JVM Scala 2.13; at most ten selected artifact coordinates per project, chosen by direct dependent-package counts; closed seed-only traversal through at most three edges. Selection remains a global popularity proxy, while exposure counts only verified relationships inside the seed.

The initial run explicitly reused `output/runs/20260907T111730789679Z/evidence` and fetched missing responses. It completed collection in **346.82 seconds (5 minutes 47 seconds)**, with analysis and rendering adding less than a second. This is a cache-backed measurement, not a fresh-crawl benchmark or a runtime guarantee.

One cached transient release failure was retried successfully. Five pending commit-history responses were also retried and remained HTTP 202. Original evidence was preserved; the reviewed cache is `output/reviewed-evidence`. A final replay using that cache and source commit `2b8a634` completed collection in 12.79 seconds. The snapshot records its seed hash, code revision, source hash, timestamps and request references. Cached responses retain their original retrieval times; the snapshot timestamp is not a claim that every source was fetched anew.

## Results and sizes

| Measurement | Observed |
| --- | ---: |
| Selected coordinates | 1,297 |
| Recorded version nodes | 1,945 |
| Recorded dependency edges | 4,590 |
| Verified repository relationships | 1,036 |
| Projects with known Value | 279 / 279 |
| Projects with known Maintenance | 231 / 279 |
| Projects with known Security | 156 / 279 |
| Referenced HTTP responses | 5,080 |
| Final SQLite database | 9,314,304 bytes |
| Referenced compressed evidence | 164,059,638 bytes |
| Standalone preview | 689,918 bytes |

Initial-run phase measurements: latest-release resolution 30.11 seconds, forward dependency collection 91.57 seconds, health cache replay 0.11 seconds, analysis 0.23 seconds and rendering 0.02 seconds. The remaining collection time includes inventory and artifact-ranking work. Final measurements and validation counts are saved alongside the final database.

## Coverage limitations reviewed

There are **297 recorded gaps**. These are not all distinct missing projects and should not be added to score-coverage counts:

- 194 fetch gaps: 189 HTTP 404 responses and five pending HTTP 202 commit-history responses. No transient 522 response remains in the final snapshot.
- 44 release gaps: latest-release eligibility or availability prevents a starting footprint under the selected matrix/coordinates. No older release was substituted.
- 41 artifact-selection gaps: 448 candidates requiring ranking have unknown dependent-package counts; 25 of those candidates were selected using the documented unknown-last, coordinate-name fallback. Repository mapping changes and index coverage can leave counts unavailable. These are not observed zeros.
- 15 version gaps: neither the version API nor POM supplied usable data.
- Three unresolved declaration gaps.

Maintenance and security remain unknown when coverage/freshness rules are not met. The report is a bounded pilot, not complete Maven-wide exposure. Missing or omitted artifacts, unsupported declarations, the three-hop limit and the closed seed can all reduce observed exposure.

## Verification

The normal pipeline validation passed. Additional real-data checks confirmed the ten-artifact selection limit, correct ranking order and unknown handling, selected-coordinate membership of traversed edges, seed-only beneficiaries and database referential integrity.

The standalone report was opened directly from disk with browser networking disabled. Browser checks exercised all 279 ranking entries, search and project selection, rendered mathematics, path expansion/collapse and repository links configured for new tabs. Light and dark layouts were checked at 360px and 1440px widths without horizontal overflow or JavaScript errors; screenshots were inspected. The HTTP preview server's missing favicon was unrelated to report functionality.

The report summary was corrected during review to count selected coordinates rather than auxiliary artifact metadata rows. Local validation passed all 47 tests, Ruff and ty. Real-data audit and browser artifacts are retained under `output/live-verification/`.
