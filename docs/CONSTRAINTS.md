# Current pilot constraints

Last updated: 2026-09-07. This is the current constraints register. It supersedes broader scope described in historical task entries. Update this file in the same change as any adjustment to selection, collection or traversal limits, and keep the seed configuration, methodology, preview labels and relevant tests consistent.

## Dimensions and caps

| Dimension or limit | Current setting | Meaning and enforcement |
| --- | --- | --- |
| Platform | JVM only | `matrix.jvm` in `config/seeds.yaml`. Scala.js and Scala Native are excluded from the current matrix. |
| Scala binary version | 2.13 only | `matrix.jvm.scala` in the seed YAML. This is a cross-build dimension, distinct from a library's release version. |
| Artifacts per project | At most 20 candidate coordinates | Expand configured module families using the matrix, sort coordinates lexicographically, then take the first 20 before checking publication availability. No backfill for missing coordinates. Enforced by `SeedConfig.coordinates()`. This is not a top-20 ranking by downstream value. |
| Seed projects | At most 380 | Five slots per each of the 76 captured subsections, replacing the earlier 100-project cap. Validation enforces the 380 ceiling. Current frozen seed: 279 repositories. |
| Projects per subsection | At most 5 | First five eligible projects in source order per subsection, then repository deduplication. Shared projects occupy a slot in every selecting subsection; no backfill after deduplication. No separate main-section quota. |
| Traversal universe | Closed seed universe | Only selected seed coordinates may be roots, intermediate nodes or targets. Only seed repositories contribute exposed Value. No Maven-wide reverse discovery is invoked. |
| Universe size | At most 7,600 candidate coordinates across at most 380 projects | Derived ceiling. Current frozen seed: 279 projects and 1,773 distinct candidate coordinates. Availability and latest-release checks can reduce the usable set. |
| Recursive dependencies per project | No separate numeric cap | Traversal stays within the selected universe and hop limit. At repository level, a seed can reach at most 278 other repositories with the current 279-project seed. That is a derived ceiling, not a limit on dependency declarations or artifact versions. |
| Total recursive dependency resolutions | No separate numeric cap | Specific historical versions of the same coordinate can require separate resolution. Coordinate and project caps do not bound requests to 1,773 or 7,600. Duplicate version nodes are fetched once per collection traversal; cached responses can be reused explicitly. |
| Transitive resolution depth | At most 3 dependency edges | Enforced by collection and analysis. A → B is one hop; A → B → C → D is three. Paths beyond three hops do not qualify. |

The module list in the YAML may contain more than 20 families for a project. It is the expanded, capped coordinate list that is collected. Raw inventories and evidence responses may mention additional artifacts; those do not enlarge the traversal universe. Collection batch size is an operational setting, not a dependency cap.

## Version and dependency semantics

Each seed starts from its latest project release. If that release has no selected Scala 2.13 coordinates, record a gap rather than substitute an older release. Intermediate dependencies retain their actual declared versions; they are never upgraded to latest during traversal. A target can match any version of its selected coordinates.

Direct compile, runtime, test, build, development and provided dependencies are eligible. Beyond the first hop, follow compile/runtime dependencies with confirmed nonoptional declarations. Thus supporting runtime libraries of a direct test framework can qualify, provided every coordinate remains inside the selected universe. Unresolved version or scope information does not establish a verified path.

Exposed Value is seed-only and repository-deduplicated. It does not estimate all Maven consumers. Omitting projects, coordinates or paths can reduce measured exposure.

## Maintaining the register

When changing a constraint:

1. Update this register and the applicable configuration or implementation together.
2. Update README/methodology explanations, generated preview labels and relevant regression tests.
3. Run `uv run scala-security plan` to refresh the offline counts reported here. Candidate counts are not observed publication counts or request estimates.
4. Record whether a real snapshot has been rebuilt under the changed constraints. Existing reports retain their original scope until rebuilt.

Current snapshot status: no real-data report has been rebuilt under these constraints. Data collection remains stopped pending a user request.
