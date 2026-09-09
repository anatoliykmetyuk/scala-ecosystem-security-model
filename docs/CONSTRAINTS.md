# Current pilot constraints

Updated 2026-09-09. Maintain this register together with configuration, implementation, preview labels and tests. Earlier run documents describe historical snapshots.

| Dimension or limit | Current setting |
| --- | --- |
| Enabled platforms | JVM and sbt; optional Scala.js/Native supported by configuration |
| Enabled compatibility cells | JVM 2.13/3; sbt Scala 2.12 + sbt 1.0, Scala 3 + sbt 2 |
| Seed selection | All eligible projects across all 76 Awesome Scala subsections and all listing pages, deduplicated by repository |
| Project ceiling | No numeric quota; bounded by eligible Awesome Scala membership; current frozen count 548 |
| Artifacts per project | At most 50 candidate coordinates per seed inventory across all enabled cells combined |
| Artifact ranking | `dependent_packages_count` descending, unknown last, deterministic cell balancing only within cutoff ties |
| Traversal universe | Closed seed universe: only selected coordinates may be roots, intermediates or targets |
| Coordinate ceiling | 50 × frozen project count (27,400 for 548 projects); publication availability and deduplication reduce this |
| Maximum dependency depth | Five edges: A → B → C → D → E → F is five hops |
| Recursive dependencies per project | No separate numeric cap beyond the closed universe and hop limit |
| Total version resolutions / HTTP requests | No separate numeric cap; different historical versions of a coordinate require separate resolution |

Observed suffixed coordinates remain target candidates independently of latest-release publication; unsuffixed candidates require verified publication and matrix evidence. [METHODOLOGY.md](METHODOLOGY.md#artifact-resolution-and-selection-authoritative) is authoritative for coordinate forms, unsuffixed filters, sbt compatibility, fixed-seed tie balancing and evidence handling. The coordinate cap is not a cap on POM requests, parents/BOMs, or historical versions.

## Version and scope rules

Start each project from its latest project release overall. If it has no selected coordinates, record a gap instead of substituting an older release. Intermediate dependencies use their actual declared versions, never an upgrade to latest. A target can match any version of its selected coordinates, including coordinates no longer published at that target project's latest release. The 50-coordinate selection policy may legitimately remove old paths; there is no additive guarantee.

Direct compile/runtime/test/build/development/provided dependencies are eligible. Later hops follow compile/runtime dependencies with confirmed nonoptional declarations. Unresolved declarations do not establish verified paths. Versions attributed to repositories outside the seed roster, or with unresolved ownership, cannot bridge paths. Ownership is resolved per publication version, with POM SCM evidence preferred over package metadata. Count each dependant repository once per target, with no self-exposure.

The pipeline collects forward dependencies and derives dependants locally. No Maven-wide reverse discovery is invoked. Cache reuse is explicit; cached failures and original retrieval timestamps remain visible. Project and artifact limits do not guarantee a runtime.

## Historical snapshot

The September 8 snapshot covered 548 projects, 5,661 distinct coordinates and 3,648 verified relationships. All eligible repositories, including ZIO and Mill, use the same selection criteria. The final incremental collection reused the preceding full-list cache and took 4 minutes 10 seconds. See [INCLUSIVE-RUN.md](INCLUSIVE-RUN.md); [FULL-RUN.md](FULL-RUN.md) records the preceding 529-project checkpoint.
