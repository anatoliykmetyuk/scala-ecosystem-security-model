# Current pilot constraints

Updated 2026-09-08. Maintain this register together with configuration, implementation, preview labels and tests. Earlier run documents describe historical snapshots.

| Dimension or limit | Current setting |
| --- | --- |
| Platform | JVM only |
| Scala binary versions | 2.13 and 3 |
| Seed selection | First ten eligible projects per each of 76 Awesome Scala subsections, in source order; repository deduplication without backfill after deduplication |
| Project ceiling | 760, derived from 76 × 10; actual frozen count reported by `scala-security plan` |
| Artifacts per project | At most 20 published coordinates across both Scala versions combined |
| Artifact ranking | `dependent_packages_count` descending, unknown last, coordinate-name ties |
| Traversal universe | Closed seed universe: only selected coordinates may be roots, intermediates or targets |
| Coordinate ceiling | 15,200 across at most 760 projects; availability and deduplication reduce this |
| Maximum dependency depth | Five edges: A → B → C → D → E → F is five hops |
| Recursive dependencies per project | No separate numeric cap beyond the closed universe and hop limit |
| Total version resolutions / HTTP requests | No separate numeric cap; different historical versions of a coordinate require separate resolution |

Expand all configured module families, then check publication availability before ranking and capping. When at most twenty published candidates exist, retain all without extra ranking-metadata requests. Record ranking inputs and decisions in SQLite; missing counts remain unknown. Inventory plots use the uncapped inventory. Package popularity is a global, historical direct-package proxy, not the final seed-only exposed Value.

## Version and scope rules

Start each project from its latest project release overall. If it has no selected coordinates, record a gap instead of substituting an older release. Intermediate dependencies use their actual declared versions, never an upgrade to latest. A target can match any version of its selected coordinates.

Direct compile/runtime/test/build/development/provided dependencies are eligible. Later hops follow compile/runtime dependencies with confirmed nonoptional declarations. Unresolved declarations do not establish verified paths. External coordinates cannot bridge paths. Count each dependant repository once per target, with no self-exposure.

The pipeline collects forward dependencies and derives dependants locally. No Maven-wide reverse discovery is invoked. Cache reuse is explicit; cached failures and original retrieval timestamps remain visible. Project and artifact limits do not guarantee a runtime.

## Snapshot status

Expansion and collection are in progress. The previously published report describes the 279-project, Scala 2.13, ten-artifact, three-hop snapshot until the expanded report is validated and published. See `docs/PILOT-RUN.md` for that historical run.
