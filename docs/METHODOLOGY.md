# Methodology

Current dimensions and limits are maintained in [CONSTRAINTS.md](CONSTRAINTS.md). Update that register whenever the implemented scope changes.

## Population and curated selection

Select the first ten eligible projects independently from each of the 76 Awesome Scala subsections, then deduplicate without backfill. The ceiling is 760 projects. This is a curated source-ranked cohort, not a statistical population sample.

Scaladex category membership is author-editable. Its default ranking combines stars with Scala source percentage; it is not a maintenance/security assessment. The frozen configuration records source rank, category URL, selection date, module families and language evidence. Eligibility requires Scala cross-build publications mapped by Scaladex and Scala as the largest language in GitHub's source-language byte statistics. Mixed-language repositories qualify only when Scala is largest; otherwise they are excluded with a recorded reason. This is an explicit conservative operational classification, not proof that every repository file is Scala. Generated/vendor content and index coverage can affect it. Compiler/nonstandard artifact coverage depends on Scaladex's maintained mappings. Overrides should be explicit reviewed changes to the YAML, never silently inferred.

Sources:
- https://index.scala-lang.org/awesome
- https://github.com/scalacenter/scaladex/blob/main/modules/server/src/main/scala/scaladex/server/route/AwesomePages.scala
- https://github.com/scalacenter/scaladex/blob/main/modules/infra/src/main/scala/scaladex/infra/ElasticsearchEngine.scala
- https://index.scala-lang.org/api/doc/

## Artifact resolution and selection (authoritative)

This section specifies the current implementation. Historical run reports retain their original settings. A project is a GitHub repository; an artifact identity is an exact Maven `groupId:artifactId`, with versions tracked separately. The frozen repository roster is unchanged by rebuilds.

### Module families and matrix cells

Seed schema 2 stores unsuffixed module families. Ordinary JVM suffixes (`_2.13`, `_3`), Scala.js suffixes (`_sjs1_3`), Native suffixes (`_native0.5_3`), and complete sbt suffixes are separate publication forms. A plugin suffix must be removed as a whole when deriving a module family; `plugin_sbt2_3` becomes `plugin`, not `plugin_sbt2`. Full compiler-version suffixes and prerelease sbt compatibility suffixes are not inferred.

The committed matrix enables JVM Scala 2.13 and 3, plus explicit sbt variants `{scala: "2.12", sbt: "1.0"}` and `{scala: "3", sbt: "2"}`. Scala.js and Native cells are supported when explicitly configured with their platform versions and Scala lines. sbt variants are pairs, not a Cartesian product. sbt `1.0` denotes the sbt 1.x compatibility line and resolves `_2.12_1.0`; sbt `2` denotes stable sbt 2.x compatibility and resolves `_sbt2_3`. This does not enable ordinary JVM Scala 2.12 libraries. A plugin's own release can be a prerelease while its compatibility suffix is stable.

### Discovery and release verification

Resolve the latest project release first, using Scaladex's project-wide `versions/latest` response. Do not invent a numeric latest ordering or fall back to an older release for missing modules. Where Scaladex has no latest response, the existing Maven repository lookup uses the newest publication date to choose one release number. Missing or conflicting release evidence is a gap.

Scaladex inventory and latest-release records establish observed suffixed coordinate candidates. Intersect them with configured module/matrix expansions. A suffixed coordinate remains eligible for ranking when it is in that inventory and matches an enabled cell, even if it is absent at the project's latest release. A missing latest release prevents consumer qualification, not historical target discovery. Actual reached versions retain exact POM/version-API evidence; inventory does not by itself establish a dependency path.

Additionally try each exact unsuffixed seed module at the chosen latest release and verify its POM identity and direct-library matrix membership. For an unsuffixed coordinate already present in inventory, a missing latest-project POM may use the package API's exact `latest_release_number` to verify a historical publication for target classification. This is never substituted as a consumer root. An unobserved guessed unsuffixed coordinate requires a valid same-project-release POM. No JARs are downloaded, no declared target versions are upgraded, and missing or mismatched POMs remain recorded gaps. `publications.version` records the actual classification publication.

The latest release restriction applies **only to the dependant's root**. It does not require a target or intermediate coordinate to publish at its owner's latest release. For example, old `com.typesafe.play:play_2.13:2.8.2` remains eligible even if Play's latest release uses `org.playframework` coordinates. Matrix eligibility and the 50-coordinate cap still apply; their exclusions are intentional policy limitations.

### Unsuffixed JVM inclusion filters

Resolve immediate declared dependency names and versions from the POM, using local/inherited properties and dependency management, including imported BOM management where needed. A dependency-management entry alone is not a direct dependency. Parent-declared inherited dependencies are immediate effective declarations. Preserve their unresolved declarations through inheritance, then apply the child's dependency management and properties; do not freeze a managed version from the parent. An explicit inherited dependency version still wins over management. As in Maven, a matching child dependency or dependency-management entry replaces the parent entry; absent fields are then resolved from the effective management/defaults, not copied from the replaced entry. Dependencies of a library are never traversed to determine matrix membership.

A direct `org.scala-lang:scala-library:2.13.x` matches JVM Scala 2.13; other configured Scala 2 lines use their major/minor version. A direct `org.scala-lang:scala3-library_3:3.x` or `org.scala-lang:scala-library:3.x` matches JVM Scala 3. These filters are independent: both declarations match both enabled cells. The coordinate is selected and counted once, even when it belongs to multiple cells. These are dependency-based inclusion rules, not compiler detection or universal binary compatibility guarantees. They do not imply Scala.js or Native membership.

The standard libraries themselves are exceptions: `org.scala-lang:scala-library` is classified by its own Scala 2 version line or Scala 3 major version, and `org.scala-lang:scala3-library_3` by its own Scala 3 version. They do not need a self-dependency. A verified publication with unknown or disabled membership is excluded from matrix selection but its dependency declarations, POM sources and classification issues remain in `publications`.

Gatling `io.gatling:gatling-core:3.15.1` is unsuffixed and declares Scala library 2.13.18. `org.scala-lang:scala-library:2.13.18` is also unsuffixed. Neither should be replaced by a guessed `_2.13` coordinate.

### sbt metadata and ownership

Modern verified sbt suffixes establish the explicit compatibility cell. Legacy unsuffixed publications require both `scalaVersion` and `sbtVersion` POM properties with supported numeric compatibility lines. Missing or prerelease-specific compatibility evidence remains unresolved; an arbitrary unsuffixed Scala library is never classified as an sbt plugin. Explicit sbt metadata prevents a disabled sbt variant from leaking into ordinary JVM inclusion.

Examples of verified published names are `com.github.sbt:sbt-web_2.12_1.0:1.5.8` and `com.thesamet:sbt-protoc_sbt2_3:1.1.0-RC2`. The latter has a prerelease project version but a stable sbt 2 compatibility suffix. Offline fixtures retain these POMs and their source URLs. Keep distinct exact coordinates distinct. The implementation does not collapse different legacy/modern coordinates merely because their names or dependency lists resemble one another; there is no unverified alias deduplication.

Ownership is resolved **per exact publication version**, independently of coordinate selection. A verified POM's GitHub SCM fields are primary evidence; absent SCM inherits the parent's SCM. If no supported SCM repository is available, ecosyste.ms package repository metadata is a recorded fallback. Conflicting supported SCM owners remain unresolved. Repository names outside the seed roster are canonicalized through GitHub's repository API (including redirects); distinct repositories are not equated merely because they share an organization or artifact prefix. All ownership sources and status are stored in `version_ownership`. Missing ownership remains unknown; an inventory claim alone does not resolve it.

For example, `scala-library:2.13.18` names `scala/scala`, while `scala-library:3.8.4` names `scala/scala3`. Do not assign one owner to every version of that artifact, or infer ownership solely from the version number. Roots, intermediates, terminal attribution and coverage use the resolved version owner. A version owned outside the frozen seed cohort cannot establish or bridge a relationship, even if its coordinate was claimed by a seed inventory. No automatic roster expansion occurs. Historical snapshots without this ownership policy remain readable under their original attribution rules.

### Ranking and deterministic tie balancing

The cap is **50 candidate coordinates per seed repository**, across all cells combined. It is a discovery/selection budget, not an ownership assignment. There is no additive preservation guarantee: reranking or changed matrix eligibility may evict previously selected coordinates and remove their paths. Rank by ecosyste.ms `dependent_packages_count` descending; known zero precedes unknown. The metric is a global direct-package popularity proxy, not seed-only exposed Value. When all eligible artifacts fit, retain them without requesting ranking metadata.

Only a tied group crossing the cutoff is balanced. Give the next slot to the least-represented non-exhausted cell, resolving equal cell priorities by SHA-256 of `scalaland-artifact-selection-v1:<cell identity>`. Within that cell choose the remaining coordinate with the smallest SHA-256 of `scalaland-artifact-selection-v1:<full coordinate>`. A selected multi-cell artifact credits every membership and is removed from every queue, consuming exactly one slot. This spreads representation as evenly as memberships and population sizes permit, redistributing exhausted-cell slots. Representation starts afresh within the cutoff group; no platform quotas override strictly higher counts. Unknown counts form their own final tied group. Complete groups and excluded remainders use the same coordinate hash for deterministic order.

Identical input data gives identical results independent of input order. Cell identities combine the platform name and full publication suffix, such as `jvm:_3` or `sbt:_2.12_1.0`. `artifact_selection` records rank, selection, count, source and policy; `publications` records release, verification, all enabled memberships, dependency evidence and issues. Raw responses remain in evidence. The seed and algorithm above make each decision reproducible. A Play-like zero-count tie no longer prefers `_2.13` alphabetically; unequal counts can still exclude Scala 3 publications.

## Dependency traversal

The universe is closed: only selected seed coordinates may be roots, intermediates or targets. No Maven-wide reverse discovery runs. Every dependant starts at its latest project release; each dependency keeps its exact declared version. Maximum path length is **five edges**. Targets match any exact version of their selected coordinates. Do not upgrade intermediates or transitively close repository-level fallout sets.

For example, Finagle at its latest release can depend on `scala-library:2.13.6` and qualify as a dependant of `scala/scala` even when library discovery verified 2.13.18. Conversely, if A latest uses B v1 and only B v2 uses C, A does not become a dependant of C through B v2.

First hops permit compile/runtime/test/provided/development/build declarations, including root optional dependencies. Subsequent hops permit compile/runtime and require confirmed nonoptional declarations. Exact unresolved ranges/placeholders or unknown scopes do not establish a path. Each dependant repository counts once per target; self-exposure is excluded. External coordinates cannot bridge a path.

Verified POM declarations provide dependency evidence. Dependency and management merging uses `(groupId, artifactId, type, classifier)` identity, so a test-jar declaration cannot replace a normal compile dependency. Missing scope defaults to compile and missing optionality to false when relevant parent/BOM management is available. Missing parent/BOM management leaves otherwise absent fields unknown; unrelated profile or plugin warnings do not erase known defaults. Profiles are not activated by this model, and their presence remains a coverage warning. Historical versions may use the version API when a verified POM is unavailable, with the missing POM retained as an evidence warning. Parent/BOM traversal resolves declarations, not graph exposure hops. Explicit active build plugins and extensions, including inherited ones, count as build inputs. Matching child plugin entries retain unspecified inherited fields; child explicit versions take precedence. Matching child extension entries replace the parent entry, as in Maven. Plugin versions can come from effective pluginManagement, but pluginManagement alone does not activate plugins. Respect `<inherited>false</inherited>` on plugins and plugin-management entries when passing them to descendants; the declaring project still uses its own active plugin. Recompute unresolved-declaration warnings from the effective child inputs, so an excluded parent plugin does not leave a stale coverage warning. Profiles, full Maven mediation, exclusions and complete build-tool/CI execution are outside this declared-dependency model; unresolved or conditional evidence is recorded rather than labelled complete.

## Dependency coverage

Coverage describes outgoing evidence at the project's selected release, independently of incoming dependants. The snapshot records checked/verified publication counts, selected/root artifact counts, fetched/usable/resolved counts, and specific evidence reasons. A fetch alone is not proof of usable or complete dependency resolution. A successfully resolved empty dependency list is usable evidence with zero paths in the analysed scope. Missing releases, no selected matching coordinates, failed fetches and unusable declarations can leave coverage unavailable. Some usable roots with missing/unresolved evidence are partial. Historical snapshots lacking declaration-level coverage are conservatively marked incomplete; their verified paths remain intact.

On the map's exposure layer, unavailable outgoing coverage is neutral gray with diagonal hatching. Known incoming exposure values are still shown in details and used in simulations. Other metric layers preserve their own valid colors and expose coverage warnings in tooltips/details. Compromise and exposure styling takes precedence over coverage hatching; the coverage message remains accessible. Selection outlines and hover interactions remain active. Warnings derive from the current snapshot, so rerendering corrected data clears stale warnings without regenerating geography.

## Value and exposure

For stars s, provisional Value is `min(1, ln(1+s) / ln(100001))`. For consumer star counts, the freshest available package repository metadata is preferred; equal or absent timestamps use the maximum observed count as a deterministic tie-breaker. Seed repository observations can replace that count. Unknown stars remain unknown; observed zero stars yield Value zero. Exposure is the sum of Value across distinct qualifying dependant repositories. It is not the target's own star count. Missing-valued dependants are counted separately, not implicitly scored zero. This is a visibility proxy, not measured revenue or usage.

Only seed projects are health-assessed. A review candidate has at least one observed dependant and an available Maintenance or Security score below 0.50. Candidates are ranked by exposure, with repository name as deterministic tie-breaker. Other seed projects remain inspectable after the candidate ranking. No scope or weighting switches are exposed.

## Maintenance

Inputs use source observations no older than 90 days:

- Push recency R = max(0, 1 − days since push / 365), weight 0.25.
- Human author records H = min(1, past-year author records / 5), weight 0.35.
- Contributor absence factor C = min(1, records accounting for 50% of human commits / 3), weight 0.40.

Recognized bot identities are excluded using explicit name/login/email heuristics. Counts are observed author records, not proven distinct people. Available terms are weighted and renormalized; at least 65% of planned weight is required. Fresh explicit archive status overrides Maintenance to zero. Absence of data does not mean healthy or unhealthy.

## Security

Selected OpenSSF checks and weights: Dangerous Workflow 3; Code Review, Branch Protection, Token Permissions, Pinned Dependencies, Vulnerabilities 2 each; Security Policy and SAST 1 each. Available scores are divided by ten, weighted and renormalized. At least 60% of total planned weight and a scan no older than 90 days are required. Missing or −1 checks are excluded, not scored zero.

These weights are provisional and are not the official OpenSSF aggregate. Detected practice gaps are not proof of exploitable vulnerabilities. Maintenance and Security use no star counts. Both sections in the report show readable observations and rendered formulas, including actual substituted terms when a score exists.

## Storage, reproducibility and evidence

SQLite stores normalized projects, artifacts, versions, indexed edges, one observation per project/source kind, scores, rankings and path references. Full responses remain compressed in URL-addressed evidence files. A request record includes actual retrieval time and status. Reusing a cache can produce observations with different dates; the run completion date does not imply all sources were fetched then.

Every rebuild creates a new database and copies its seed configuration. Missing requests are retried a bounded number of times for transient failures. A fresh run never implicitly reuses another run's cache. An explicit cache replay retains cached failures. The preview embeds a compact normalized view and is capped at 24 MiB; exceeding the budget fails generation instead of hiding dependants. MathML requires a modern browser and no runtime CDN resources.

Raw API commit responses may contain public author identities; the report displays aggregate author counts. Source credentials are not stored. ecosyste.ms data is CC BY-SA 4.0; preserve attribution and applicable share-alike requirements when redistributing derived data. See https://ecosyste.ms/api and https://github.com/ossf/scorecard/blob/main/docs/checks.md.

## Validation

The validation command runs Ruff, ty and deterministic offline tests, including mocked collection through SQLite analysis and HTML generation. Regression cases cover version consistency, historical reverse discovery, five hops, source categories/eligibility, caches/pagination, POM interpretation, score coverage, Java consumers and browser interactions. Database checks verify foreign keys, score bounds, exposure sums, root release identity and every retained path's continuity, scope and depth. Tests establish implementation properties, not empirical validation of the provisional health model.

## Metric attribution

CHAOSS [Contributors](https://www.chaoss.community/kb/metric-contributors/) informs the human-author input, restricted here to apparent commit-author records rather than all contribution types. The absence-factor input follows [CHAOSS Contributor Absence Factor](https://www.chaoss.community/kb/metric-contributor-absence-factor/), applied to observed human commits. Push recency, normalization thresholds, component weights and the aggregate Maintenance score are pilot-defined, not official CHAOSS scores.

Security inputs come from [OpenSSF Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md). This pilot defines its own weighted aggregate. Provisional Value and Exposed Value are also pilot-defined. Calculation panels link the external concepts directly and label these adaptations.
