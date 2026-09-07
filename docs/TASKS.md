# Implementation status and remaining work

Last reviewed: 2026-09-07.

Implementation, collection and real-report verification are complete. See [PILOT-RUN.md](PILOT-RUN.md) for final snapshot identity, measured runtime, coverage limitations and verification. No collection process remains running.

[CONSTRAINTS.md](CONSTRAINTS.md) is the maintained register of dimensions and limits. Update it together with configuration, implementation, documentation and relevant tests whenever a constraint changes.

## Current scope

- Frozen seed: 279 unique Scala projects, selected from the first five eligible entries in each of 76 Awesome Scala subsections, then deduplicated without backfill. The selection ceiling is 380 projects. The current seed was reselected offline from previously captured source data.
- Matrix: JVM, Scala 2.13 only. The YAML stores unsuffixed module families separately from the shared matrix.
- Artifact selection: at most 10 published coordinates per project, ranked by `dependent_packages_count` descending. Unknown counts follow known counts, including zero; ties use coordinate name. Projects with ten or fewer eligible coordinates retain all of them without a ranking-metadata request. Save counts, ranks, decisions and source references in SQLite.
- Offline expansion: 2,596 distinct uncapped candidate coordinates, or 2,606 project–artifact entries. The selected-entry upper bound is 1,297; actual selection requires publication and ranking metadata. Artifact inventory plots remain uncapped.
- Closed seed universe: only selected seed coordinates may be roots, intermediates or targets. Only seed repositories contribute exposed Value. Collect forward dependencies and derive dependants locally; do not invoke Maven-wide reverse discovery.
- Maximum path length: three dependency edges. This is not a separate cap on historical versions or HTTP requests.
- Start from each project's latest release overall. If it has no selected matrix coordinates, record a gap rather than substitute an older release. Follow actual intermediate versions without upgrading them. A target matches any version of its selected coordinates.
- Direct compile, runtime, test, build, development and provided dependencies are eligible. Subsequent edges must be compile/runtime with confirmed nonoptional declarations. Unresolved declarations do not establish verified paths.
- Rank exposure using the sum of provisional Value across distinct qualifying seed dependants. No scope or exposure-weight switches. Global dependent-package counts select artifacts; they are not the final seed-only exposed Value.

## Completed implementation

- [x] Initialize Git and a private upstream GitHub repository, with an appropriate `.gitignore` for environments, caches and generated data.
- [x] Organize sources under `src/`, tests under `tests/`, documentation under `docs/`, configuration under `config/` and shell entry points under `scripts/`.
- [x] Manage Python and dependencies through uv, `pyproject.toml` and the committed lockfile.
- [x] Provide one validation command covering Ruff linting/formatting, ty type checking and offline automated tests. Run the same checks in GitHub Actions.
- [x] Implement deterministic subsection selection, Scala eligibility checks, repository deduplication, compact seed configuration and shared matrix expansion.
- [x] Implement publication checks and the ten-artifact ranking cap with auditable selection evidence and explicit unknown counts.
- [x] Implement forward collection inside the closed seed universe, exact-version traversal, three-hop limits and repository-deduplicated fallout.
- [x] Cover the A/B/C version-consistency example below and current selection/traversal boundaries with regression tests.
- [x] Replace large derived JSON snapshots/results with normalized SQLite storage and compressed raw HTTP evidence. Preserve provenance, missing-data semantics and explicit fresh versus cached collection.
- [x] Retain SQLite aggregation and version-aware graph traversal without introducing NumPy or Parquet into the model pipeline.
- [x] Provide `scripts/rebuild.sh` to collect, analyze, validate and generate a standalone preview; document the from-scratch workflow and explicit cache reuse in README.
- [x] Provide the offline `scala-security plan` command without constructing an HTTP client. Report uncapped candidates separately from the selected-entry upper bound.
- [x] Implement the two-column preview, prominent repository links opening new tabs, and secondary raw-evidence links.
- [x] Explain Maintenance and Security inputs separately, with rendered mathematical formulas, substituted values, coverage and unknown-score explanations. Define symbols before use and keep Maintenance, Security and Exposed Value calculations in collapsed disclosure panels.
- [x] Display dependants ranked by provisional Value with star inputs and expandable/collapsible exact-version dependency paths.
- [x] Remove scope and weight switches. Display seed-only exposure, the artifact cap and the three-hop limit.
- [x] Test offline report generation, browser interactions, formulas and responsive light/dark layouts using fixtures.
- [x] Validate the current implementation locally: 47 tests, Ruff and ty pass. Upstream CI for commit `a35ac63` passed.

## Version-consistency acceptance example

Assume A, B and C and all path coordinates are in the selected universe:

- A latest depends on B v1.
- B latest is v2 and depends on C.
- B v1 does not depend on C, and A has no other path to C.
- C's fallout includes B but excludes A.
- B's fallout includes A because A latest depends on a version of B.

Project-level fallout is not transitively closed. B being in C's fallout and A being in B's fallout does not alone place A in C's fallout.

## Completed collection and verification work

These steps were completed using an explicit cache-backed collection run and a final replay after reviewing transient failures. Known source gaps remain documented.

- [x] Collect the full frozen cohort under the current constraints, preserving existing evidence and recording whether the run is fresh or explicitly cache-backed. Fetch publication/ranking metadata, selected dependency versions and health evidence.
- [x] Validate the resulting SQLite database, including selection limits, seed-only path membership, version consistency, exposure sums and missing-data handling. Investigate failures and material coverage gaps before claiming completion.
- [x] Generate the actual standalone report from that database and inspect rankings, evidence, formulas, repository links, expanded paths and responsive light/dark layouts using real data.
- [x] Record actual collection, traversal and scoring timings, storage sizes, selected coordinate/version counts and coverage gaps. Do not promise a runtime based solely on the coordinate cap.
- [x] Update final documentation and snapshot status with the observed results. Commit and push any resulting source/documentation changes and confirm CI passes for those changes.

## Authorization and exclusions from scope

The user explicitly granted blanket, unlimited permission on 2026-09-07 to commit and push work on this project. This overrides the earlier requirement for separate permission for each commit or push. Continue to omit AI attribution from commit messages and authors.

Website deployment and hosting remain out of scope. Do not set up Cloudflare, GitHub Pages or deployment workflows. The private source repository, validation-only CI and local standalone preview remain in scope.
