# Current pilot constraints

Last updated: 2026-09-07. This is the current constraints register. It supersedes broader scope described in historical task entries. Update this file in the same change as any adjustment to selection, collection or traversal limits, and keep the seed configuration, methodology, preview labels and relevant tests consistent.

## Dimensions and caps

| Dimension or limit | Current setting | Meaning and enforcement |
| --- | --- | --- |
| Platform | JVM only | `matrix.jvm` in `config/seeds.yaml`. Scala.js and Scala Native are excluded from the current matrix. |
| Scala binary version | 2.13 only | `matrix.jvm.scala` in the seed YAML. This is a cross-build dimension, distinct from a library's release version. |
| Artifacts per project | At most 10 selected coordinates | Expand all configured modules, check published JVM Scala 2.13 coordinates, then select at most 10 by `dependent_packages_count` descending. Known counts (including zero) precede unknown counts; ties use coordinate name. Projects with ten or fewer published candidates keep all candidates without a ranking-metadata request. Enforced during collection; offline expansion remains uncapped. |
| Seed projects | At most 380 | Five slots per each of the 76 captured subsections, replacing the earlier 100-project cap. Validation enforces the 380 ceiling. Current frozen seed: 279 repositories. |
| Projects per subsection | At most 5 | First five eligible projects in source order per subsection, then repository deduplication. Shared projects occupy a slot in every selecting subsection; no backfill after deduplication. No separate main-section quota. |
| Traversal universe | Closed seed universe | Only selected seed coordinates may be roots, intermediate nodes or targets. Only seed repositories contribute exposed Value. No Maven-wide reverse discovery is invoked. |
| Universe size | At most 3,800 selected coordinates across at most 380 projects | Current 279-project seed has 2,596 distinct uncapped candidates (2,606 project–artifact entries) and an upper bound of 1,297 selected entries. Final selection depends on publication and ranking metadata. |
| Recursive dependencies per project | No separate numeric cap | Traversal stays within the selected universe and hop limit. At repository level, a seed can reach at most 278 other repositories with the current 279-project seed. That is a derived ceiling, not a limit on dependency declarations or artifact versions. |
| Total recursive dependency resolutions | No separate numeric cap | Specific historical versions of the same coordinate can require separate resolution. Coordinate and project caps do not bound requests to 1,297 or 3,800. Duplicate version nodes are fetched once per collection traversal; cached responses can be reused explicitly. |
| Transitive resolution depth | At most 3 dependency edges | Enforced by collection and analysis. A → B is one hop; A → B → C → D is three. Paths beyond three hops do not qualify. |

The module list in the YAML may contain more than 10 families for a project. All matrix-matching published candidates are eligible for metadata ranking; only the selected top ten enter dependency traversal. Artifact-count plots use the uncapped inventory. Raw inventories and evidence responses may mention additional artifacts; those do not enlarge the traversal universe. Collection batch size is an operational setting, not a dependency cap.

Ranking uses global direct dependent-package counts as a selection proxy, not the final seed-only exposed Value. It can include historical releases, cross-builds and internal modules. Selection counts, ranks, decisions and sources are saved in SQLite, with raw metadata pages in evidence.

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

Current snapshot status: collection and report verification completed on 2026-09-07. The final snapshot selected 1,297 coordinates. See [PILOT-RUN.md](PILOT-RUN.md) for cache provenance, measured timings and known coverage gaps.
