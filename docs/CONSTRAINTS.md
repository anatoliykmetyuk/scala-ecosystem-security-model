# Current pilot constraints

Updated 2026-09-08. Maintain this register together with configuration, implementation, preview labels and tests. Earlier run documents describe historical snapshots.

| Dimension or limit | Current setting |
| --- | --- |
| Platform | JVM only |
| Scala binary versions | 2.13 and 3 |
| Seed selection | All eligible projects across all 76 Awesome Scala subsections and all listing pages, deduplicated by repository |
| Project ceiling | No numeric quota; bounded by eligible Awesome Scala membership; current frozen count 529 |
| Artifacts per project | At most 50 published coordinates across both Scala versions combined |
| Artifact ranking | `dependent_packages_count` descending, unknown last, coordinate-name ties |
| Traversal universe | Closed seed universe: only selected coordinates may be roots, intermediates or targets |
| Coordinate ceiling | 50 × frozen project count (26,450 for 529 projects); publication availability and deduplication reduce this |
| Maximum dependency depth | Five edges: A → B → C → D → E → F is five hops |
| Recursive dependencies per project | No separate numeric cap beyond the closed universe and hop limit |
| Total version resolutions / HTTP requests | No separate numeric cap; different historical versions of a coordinate require separate resolution |

Expand all configured module families, then check publication availability before ranking and capping. When at most fifty published candidates exist, retain all without extra ranking-metadata requests. Record ranking inputs and decisions in SQLite; missing counts remain unknown. Inventory plots use the uncapped inventory. Package popularity is a global, historical direct-package proxy, not the final seed-only exposed Value.

## Version and scope rules

Start each project from its latest project release overall. If it has no selected coordinates, record a gap instead of substituting an older release. Intermediate dependencies use their actual declared versions, never an upgrade to latest. A target can match any version of its selected coordinates.

Direct compile/runtime/test/build/development/provided dependencies are eligible. Later hops follow compile/runtime dependencies with confirmed nonoptional declarations. Unresolved declarations do not establish verified paths. External coordinates cannot bridge paths. Count each dependant repository once per target, with no self-exposure.

The pipeline collects forward dependencies and derives dependants locally. No Maven-wide reverse discovery is invoked. Cache reuse is explicit; cached failures and original retrieval timestamps remain visible. Project and artifact limits do not guarantee a runtime.

## Snapshot status

The expanded snapshot completed on 2026-09-08: 436 projects, 3,251 distinct selected coordinates, 2,370 verified relationships. Cache-backed collection took 4 minutes 37 seconds, excluding seed selection. See [EXPANDED-RUN.md](EXPANDED-RUN.md) for measurements and coverage limitations.
