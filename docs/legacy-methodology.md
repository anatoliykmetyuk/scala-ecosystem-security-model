# Pilot methodology, version 0.1

## Question and unit of analysis

Which components with weak observable maintenance capacity or security practices support the most value in a selected Scala cohort?

Dependency evidence is stored as exact Maven artifact-version declarations. Health is assessed at the GitHub repository level, with package-to-repository assignments supplied by ecosyste.ms. Packages without a usable GitHub mapping remain separate components with unknown health. Repository redirects reported by the repository API are normalized. These assignments need expert review, especially forks, historical packages, monorepos, and moved projects.

## Selection

`collect.py` contains a deliberate 40-artifact sample covering language implementations, standard modules, functional libraries, JSON, HTTP, data access, testing, build tooling, utilities, JVM infrastructure, Spark, and scientific computing. Selection used the partner inventory and category coverage, not a random sample or a claim of ecosystem representativeness. Scala 2.13 JVM artifacts predominate to keep paths compatible; Scala 3 compiler, Scala.js, and sbt are deliberate exceptions. Scala Native and private applications are not covered. One artifact does not describe a project's full dependency footprint.

Seeds use the latest version returned by the ecosyste.ms endpoint at collection time. This can differ from an upstream project's newest supported/pre-release line. Versions are frozen in `snapshot.json`. Do not interpret the graph as the dependency footprint of every installed version.

## Graph and exposure

All direct seed declarations are recorded. Up to two dependency layers are fetched after the seeds, recording edges out to three hops. Only exact requirements are traversed. Ranges, placeholders, missing versions, optional dependencies, and unknown scopes never silently resolve to latest. The collector caps fetched versions at 1,200 and records omissions. Boundary targets can be included in exposure because the incoming declaration was observed, even when their own dependencies were not fetched.

Every fetched version is checked against its published Maven Central POM. When a direct dependency can be matched unambiguously, its explicit POM scope and optional flag override the API fields, with original values preserved. For standalone POMs without a parent or dependencyManagement, omitted fields default to compile/nonoptional under Maven's rules. Where inheritance could affect defaults, the API value is retained unless the POM is explicit. An API-null scope is not assumed to mean compile without this evidence. Direct POM declarations are retained for coverage checks; inherited dependencies still rely on ecosyste.ms metadata. The collector does not independently implement parent/BOM/property resolution.

- Runtime mode traverses nonoptional runtime/compile edges.
- Broader mode additionally traverses direct nonoptional test, development, provided, and build edges from each seed. Subsequent steps use runtime/compile only. This models the dependencies needed to use direct tools/tests; it does not recursively include every dependency's test suite.
- No mode claims to cover CI actions, publishing credentials, registries, or complete sbt build infrastructure. Those require a later targeted pass.
- Paths are computed on artifact-version IDs before aggregation to repository components. A path through one version cannot continue through another version's outgoing edges.
- Each seed project contributes once per target component, regardless of duplicate paths, artifacts, or versions. A project does not contribute exposure to itself. Cycles terminate. A shortest observed path is retained for each beneficiary.

This is a declared-dependency reachability model, not Maven/sbt/Coursier conflict resolution. Exclusions, platform constraints, mediation, profiles and actual deployment reachability are not modeled. Three-hop boundaries and omitted requirements miss paths; overapproximation from unresolved build semantics can add paths. Consequently the results are not mathematical lower bounds on real exposure.

## Value

`V = min(1, ln(1 + repository stars) / ln(100001))`.

This is an explicitly provisional visibility proxy. Stars do not measure industry usage or economic value. Missing stars leave V unknown. There is no zero substitution for absent metadata. Partner dependent counts are retained in the original files but excluded from the formula because their aggregation is ambiguous and because using dependency-derived importance again in downstream exposure can amplify centrality twice.

For each target, exposed cohort value is the sum of V over distinct reachable seed projects. It is not normalized to 0-1, money, probability, or ecosystem-wide impact. Unknown-valued beneficiaries are counted separately. The equal-weight alternative counts distinct seed projects and reports a separate rank to reveal sensitivity to Value assumptions. Seed selection remains a larger source of bias than these weights.

## Maintenance Health

CHAOSS-informed measurements, using ecosyste.ms repository and commit indexes:

| Input | Normalization | Weight |
|---|---|---:|
| Repository push recency | max(0, 1 - days since push / 365) | 0.25 |
| Apparent human author records in source's past-year window | min(1, authors / 5) | 0.35 |
| Contributor absence factor | min(1, authors responsible for at least half the human commits / 3) | 0.40 |

Known bot labels/names are excluded using the explicit heuristic in `analyze.py`. Identities are not perfectly deduplicated and bots can be missed. Counts represent source author records, not verified unique people or maintainers. No personal rankings are produced. Past-year windows are relative to the source snapshot, not necessarily the pilot collection date.

Weights are renormalized over available inputs only if at least 65% of planned weight is present. Repository and commit sources older than 90 days are excluded from scoring. A fresh explicit archived=true sets M=0, signaling the need to review ongoing maintenance responsibility, not proof of insecurity. Inactivity can be appropriate for mature software, so low M requires expert interpretation. Recent pushes can be automated and are only a small part of the score.

Issue/PR summaries are retained as diagnostics only. Their closure-time averages are not first-human-response times, their observation windows may be incomplete, and bot activity is substantial in some repositories. Release dates also remain evidence rather than an automatic penalty. We do not claim to have implemented all CHAOSS Starter Project Health metrics.

## Security Health

S is a weighted mean of selected OpenSSF Scorecard checks, divided by 10:

| Check | Weight |
|---|---:|
| Dangerous-Workflow | 3 |
| Code-Review, Branch-Protection, Token-Permissions, Pinned-Dependencies, Vulnerabilities | 2 each |
| Security-Policy, SAST | 1 each |

These are pilot weights, not the official Scorecard aggregate or a validated risk model. Maintenance and license checks are excluded to keep the dimensions distinct. Missing checks and scores of -1 are unknown and excluded, never zero. S is withheld unless 60% of planned check weight is observed and the Scorecard snapshot is at most 90 days old. Individual reasons, details, scan date, commit and source links remain available in evidence/results.

Scorecard measures observable repository practices and has detection limitations. A low result calls for investigation, not a claim that a library is vulnerable. Its Vulnerabilities check is not a version-specific advisory audit of this pilot graph. A high result is not a security guarantee. Audit records, exploitability, response to disclosures and private evidence are absent.

## Ranking and intervention interpretation

A candidate has observed M < 0.50 OR observed S < 0.50 and at least one distinct cohort beneficiary. Candidates are ranked by exposed cohort value, with lexical ID tie-breaking. Health identifies candidates; it is not multiplied into exposure. Unknown health does not qualify as weak, but is shown separately as an evidence gap. One weak dimension can qualify even when the other is unknown. Threshold sensitivity at 0.40, 0.50 and 0.60 is reported by validation.

Proposed responses depend on evidence: maintenance-capacity review for concentrated or inactive maintenance; workflow/permission/pinning review for corresponding Scorecard findings; additional evidence collection where health is unknown. Funding and audit priorities require expert review of the observed paths and findings.

## Reproduction and provenance

Run from the project directory with Python 3 (standard library only):

```sh
python3 pilot/collect.py
python3 pilot/analyze.py
python3 -m unittest discover -s pilot -p 'test_*.py'
python3 pilot/validate.py
python3 pilot/render.py
```

Successful and failed HTTP requests are cached under `evidence/` by SHA-256 of the URL, with retrieval timestamp and URL. `snapshot.json` freezes graph and repository data; `results.json` stores derived scores, coverage and paths. The collector reuses cache, including failures, for reproducibility. To collect a new snapshot, use a separate copied pilot directory with an empty evidence directory rather than overwriting the original. The result records the snapshot hash. API requests are public read-only requests with an explicit user agent; no credentials are required or saved.

Sources:

- [ecosyste.ms API documentation](https://ecosyste.ms/api), [Packages API specification](https://github.com/ecosyste-ms/packages/blob/main/openapi/api/v1/openapi.yaml). Ecosyste.ms identifies its API data license as CC BY-SA 4.0; preserve attribution with reused data.
- [CHAOSS Starter Project Health](https://www.chaoss.community/kb/metrics-model-starter-project-health/), [Contributor Absence Factor](https://www.chaoss.community/kb/metric-contributor-absence-factor/).
- [OpenSSF Scorecard check documentation](https://github.com/ossf/scorecard/blob/main/docs/checks.md), [Scorecard API](https://api.securityscorecards.dev/).
- Partner inventories: `../data/scala_ecosystem/scala_projects.csv` and `scala_dependencies.csv`. Provenance and counting semantics were not supplied.

No project sources were modified, committed, or pushed. No maintainers were contacted.
