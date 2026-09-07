# Scala ecosystem security model

A reproducible assessment of a frozen, curated Scala cohort. It ranks projects with low observed maintenance or security scores by the summed Value of their verified Maven dependants, up to three dependency hops. The current pilot counts only dependants within its frozen seed universe.

See **[Current pilot constraints](docs/CONSTRAINTS.md)** for the maintained platform/version dimensions, project and artifact caps, traversal universe, hop limit and limits that are not separately capped.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from this repository:

```sh
uv python install 3.13
uv sync --locked
uv run playwright install chromium
```

On Linux, browser tests may require `uv run playwright install --with-deps chromium`.
Optional: sign into `gh auth login` to use authenticated public GitHub metadata requests during seed selection. Credentials are never stored in evidence or generated output. The normal rebuild uses the already-frozen seed configuration.

Optionally set `ECOSYSTEMS_CONTACT_EMAIL` to an email you authorize sending to ecosyste.ms for its polite request pool. It is sent only to ecosyste.ms hosts and is not stored in evidence.

## Rebuild from scratch

```sh
./scripts/rebuild.sh
```

This single command reads **[config/seeds.yaml](config/seeds.yaml)**, creates a fresh evidence directory and SQLite snapshot, collects dependencies and score inputs, calculates and validates results, then generates **`output/preview.html`**. Open that file directly in a browser. It embeds the required data and needs no API connection or local server to view.

This pilot traverses only selected seed coordinates, for at most three hops. It does not run Maven-wide reverse discovery. The JVM Scala 2.13 matrix and a hard cap of 20 candidate coordinates per project currently produce 1,773 candidates across 279 projects. Historical dependency versions can still require multiple requests per coordinate, so this is not a total request cap. HTTP failures and unresolved declarations are recorded as gaps.

Each run is retained under `output/runs/<UTC timestamp>/`:

- `seeds.yaml`: exact input used for this run.
- `snapshot.sqlite`: normalized collected entities, observations, calculated scores, fallout paths, rankings, gaps and request provenance.
- `evidence/`: URL-addressed gzip-compressed HTTP responses, unless explicitly reusing another directory.
- `validation.json`: verified table/path counts.
- `measurements.json`: phase timings and database, compressed evidence and preview sizes. Cache-backed runs measure replay plus missing requests, not a fresh crawl.

`output/latest-database.txt` points to the database behind the most recently generated preview. A failed rebuild does not overwrite the previous preview.

### Explicit cache reuse

To reconstruct using responses already downloaded, including after an interrupted run:

```sh
./scripts/rebuild.sh --reuse-cache output/runs/<previous-run>/evidence
```

This replays available responses, including cached failures, and fetches missing URLs. It creates a new database; it is not a fresh observation of cached URLs. Recorded request timestamps remain their actual retrieval times. Omit `--reuse-cache` to collect fresh data. Prior runs and caches are never automatically deleted.

To regenerate only the preview from an existing database, without network access:

```sh
uv run scala-security render --database output/runs/<run>/snapshot.sqlite
```

### Seeds

The editable YAML uses schema 2: repositories, subsection categories, source ranks/URLs, Scala eligibility evidence and unsuffixed module coordinates. A single shared matrix controls cross-build dimensions:

```yaml
schema: 2
matrix:
  jvm:
    scala: ['2.13']
projects:
  - repository: scala-graph/scala-graph
    categories: [Computer Science]
    modules:
      - org.scala-graph:graph-core
```

This expands `graph-core` into `graph-core_2.13`. Coordinates are sorted lexicographically and capped at 20 per project before checking publication availability, with no backfill. This is a deterministic cost limit, not a ranking by downstream value. The YAML explicitly records `universe: seed`, `max_artifacts_per_project: 20` and the selection rule. Modules beyond the cap remain editable in the YAML but are not collected. Missing coordinates are recorded in SQLite. External projects and excluded coordinates cannot contribute exposure or bridge dependency paths. Projects whose latest release has no selected coordinates are reported as gaps, without substituting an older release.

Select the first five eligible projects independently from each Awesome Scala subsection in captured source order, then deduplicate repositories. A shared project occupies a slot in every selecting subsection; there is no backfill after deduplication. The 76 subsections imply a ceiling of 380 projects, replacing the earlier 100-project cap. The current frozen seed contains 279 unique projects and expands to 1,773 candidate coordinates. The current file was reselected offline from the previously captured candidate pool (originally up to ten eligible entries per subsection), without refreshing the source. Subsections with fewer than five eligible entries in that pool remain smaller. Ordinary rebuilds preserve the frozen seed.

Inspect the expansion without any network requests:

```sh
uv run scala-security plan
```

This prints project/module counts, the matrix and the number of candidate coordinates. It does not assert that every matrix combination is published, and does not fetch data.

To intentionally replace the frozen cohort with a new source snapshot:

```sh
uv run scala-security select --seeds config/seeds.yaml --output output/selection-refresh
```

Review the YAML diff before accepting a new cohort. For a cache-backed repeat of that selection, explicitly provide `--reuse-cache <evidence-directory>`.

## Validation

```sh
./scripts/check.sh
```

Runs Ruff linting, Ruff formatting checks, ty static type checking and pytest, including offline browser tests. The same script runs in GitHub Actions on pushes and pull requests. Routine validation does not call ecosystem APIs or require a collected dataset.

To verify a collected database separately:

```sh
uv run scala-security validate --database output/runs/<run>/snapshot.sqlite
```

The shell scripts resolve the repository root themselves, so they can be invoked by absolute path from another directory. Relative command arguments are interpreted from the repository root.

## Layout

- `src/scala_security/`: collection, typed model boundaries, SQLite schema, analysis, rendering and CLI.
- `src/scala_security/templates/`: self-contained report template with native MathML formulas.
- `tests/`: graph, scores, HTTP/cache, selection, integration and browser regressions.
- `scripts/`: rebuild and validation entry points.
- `config/`: reviewed seed configuration and selection provenance.
- `docs/`: [methodology](docs/METHODOLOGY.md), implementation tasks and supporting notes.
- `model/`, `data/`: original vision documents and partner-supplied inputs.
- `output/`: ignored generated results and evidence. The earlier `pilot/` output is retained locally and ignored.

Website deployment is out of scope. The GitHub repository is private; CI validates the code and does not publish the report.
