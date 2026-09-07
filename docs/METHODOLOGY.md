# Methodology

Current dimensions and limits are maintained in [CONSTRAINTS.md](CONSTRAINTS.md). Update that register whenever the implemented scope changes.

## Population and curated selection

Select the first five eligible projects independently from each Awesome Scala subsection in captured source order, then deduplicate repositories. A shared project occupies a slot in every selecting subsection; there is no backfill after deduplication. The 76 subsections imply a ceiling of 380 projects, replacing the earlier 100-project cap. The current frozen seed contains 279 unique projects and expands to 2,596 distinct uncapped candidate coordinates (2,606 project–artifact entries). The current file was reselected offline from the previously captured candidate pool (originally up to ten eligible entries per subsection), without refreshing the source. Subsections with fewer than five eligible entries in that pool remain smaller. Ordinary rebuilds preserve the frozen seed.

Scaladex category membership is author-editable. Its default ranking combines stars with Scala source percentage; it is not a maintenance/security assessment. The frozen configuration records source rank, category URL, selection date, module families and language evidence. Eligibility requires Scala cross-build publications mapped by Scaladex and Scala as the largest language in GitHub's source-language byte statistics. Mixed-language repositories qualify only when Scala is largest; otherwise they are excluded with a recorded reason. This is an explicit conservative operational classification, not proof that every repository file is Scala. Generated/vendor content and index coverage can affect it. Compiler/nonstandard artifact coverage depends on Scaladex's maintained mappings. Overrides should be explicit reviewed changes to the YAML, never silently inferred.

Sources:
- https://index.scala-lang.org/awesome
- https://github.com/scalacenter/scaladex/blob/main/modules/server/src/main/scala/scaladex/server/route/AwesomePages.scala
- https://github.com/scalacenter/scaladex/blob/main/modules/infra/src/main/scala/scaladex/infra/ElasticsearchEngine.scala
- https://index.scala-lang.org/api/doc/

## Project and version identity

A project is a GitHub repository; artifacts are Maven group/artifact coordinates. Seed schema 2 stores module families without cross-build suffixes and a shared matrix. The current matrix permits JVM coordinates for Scala 2.13 only. Expand all configured modules, check published JVM Scala 2.13 coordinates, then select at most 10 by `dependent_packages_count` descending. Known counts (including zero) precede unknown counts; ties use coordinate name. Projects with ten or fewer published candidates keep all candidates without a ranking-metadata request. Package metadata is retrieved through paginated repository lookup, filtered to Maven Central and eligible coordinates, without reverse traversal. Only the selected published matches become target coordinates. The count is a global direct-package popularity proxy across indexed releases, not latest-release, seed-only, repository-deduplicated exposed Value. Unknown counts remain null and are reported as gaps. Selection inputs and decisions are retained in `artifact_selection`; raw responses remain in evidence. Availability is recorded per candidate in SQLite. Neither a missing variant nor an unavailable inventory triggers an unverified fallback. Historical versions of selected coordinates still match; Scala 2.12, JS/Native, full-compiler-version and unsuffixed coordinates are outside the selected target matrix. Only selected seed coordinates may appear anywhere in a path. External consumers, including Java projects, do not contribute to this pilot. When a path ends at a nonselected artifact of a seed repository, it does not qualify that repository as a target. Multiple repository claims are reconciled against ecosyste.ms package repository metadata; unresolved ownership is a reported gap.

A target matches any version of any artifact attributed to that project. A dependant qualifies only from its project's latest release overall. For Scala-indexed consumers, Scaladex's project-wide `versions/latest` response supplies that release and its published variants. This uses Scaladex's release policy, not an independently invented numeric version ordering. For non-indexed consumers, all repo-linked Maven packages are obtained from ecosyste.ms; the latest publication date identifies the release number, and only artifacts with that release number are selected. Independently versioned monorepos remain a limitation of repository-as-project/latest-release semantics. Missing or conflicting latest-release evidence excludes the consumer and records a gap.

If A's Scala 2.12 artifact ends at version 1 and its Scala 3 artifact reaches release 2, the older line is discontinued for A's current footprint. Intermediate dependencies are never upgraded: A latest → B v1 uses B v1 even when B latest is v2.

## Reverse discovery and qualification

Maximum path length is **three dependency edges**, also displayed in the preview header. Artifact selection limits the observed exposure; no claim of complete project-wide exposure is made. There is no seed-only restriction on consumers: Java and other Maven consumers contribute Value when a verified path exists.

The current pilot uses a closed seed universe. No reverse endpoint is queried. Exposure counts only other selected seed repositories and is explicitly labeled seed-only in the preview.

The collector obtains seed projects' latest releases and follows their actual declared dependency versions up to three hops, restricted at every step to selected coordinates. External nodes cannot bridge paths. Each qualifying seed repository counts once per target. Historical intermediate versions remain exact; they are never bumped to latest. The target itself is excluded from its fallout.

Acceptance example: A latest → B v1; B latest v2 → C; B v1 does not depend on C. C's fallout includes B but not A. B's fallout includes A. Project-level fallout sets are not transitively closed.

## Dependency declarations

The first hop includes compile, runtime, test, provided, development and build scopes. Subsequent hops include compile/runtime dependencies of those libraries/tools, not their own test suites. A root project’s optional declarations still count as its own dependencies; optional dependencies of intermediate libraries do not propagate. Root optionality does not change inclusion, including when that flag is missing. Unknown scope, unknown intermediate optionality and unresolved version ranges are recorded rather than silently treated as compile/latest. This follows [Maven’s optional-dependency semantics](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html).

Version API declarations are checked against direct Maven Central POM declarations. Unambiguous explicit POM scope and optionality override API fields. Local POM properties are expanded with a bounded substitution loop. Standalone POMs without parent/dependencyManagement default to compile/nonoptional. Inherited unspecified values remain dependent on API evidence. Additional direct POM declarations are retained. Explicit active POM build plugins and extensions are included as build inputs; pluginManagement entries alone do not activate a plugin. Missing plugin versions remain unresolved gaps. Maven reverse-index coverage may omit such build relationships, so discovering every project that uses a build tool is not guaranteed.

This does not implement full Maven mediation, dependency exclusions, parent/BOM resolution or profile activation. It is a declared-dependency model, not a deployment inventory or a complete sbt/CI/release infrastructure graph. Both missed and spurious paths are possible relative to actual resolved builds. HTTP failures, missing repositories, index gaps and unresolved declarations are counted in the snapshot and preview.

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

The validation command runs Ruff, ty and deterministic offline tests, including mocked collection through SQLite analysis and HTML generation. Regression cases cover version consistency, historical reverse discovery, three hops, source categories/eligibility, caches/pagination, POM interpretation, score coverage, Java consumers and browser interactions. Database checks verify foreign keys, score bounds, exposure sums, root release identity and every retained path's continuity, scope and depth. Tests establish implementation properties, not empirical validation of the provisional health model.
