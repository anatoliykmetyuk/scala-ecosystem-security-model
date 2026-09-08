# Scala ecosystem security model

A reproducible assessment of a frozen, curated Scala cohort. It ranks projects with low observed maintenance or security scores by the summed Value of their verified Maven dependants, up to five dependency hops. The current pilot counts only dependants within its frozen seed universe.

See **[Current pilot constraints](docs/CONSTRAINTS.md)** for the maintained platform/version dimensions, project and artifact caps, traversal universe, hop limit and limits that are not separately capped.

The completed cache-backed pilot and its coverage limitations are documented in **[INCLUSIVE-RUN.md](docs/INCLUSIVE-RUN.md)**. Its local report is `output/preview.html`.

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

This pilot traverses only selected seed coordinates for at most five hops, without Maven-wide reverse discovery. The cap is 50 artifacts per project, selected by dependent-package count. Current frozen counts are reported by `uv run scala-security plan`; final selection requires metadata collection. This is not a request cap. Failures are recorded as gaps.

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
    scala: ['2.13', '3']
projects:
  - repository: scala-graph/scala-graph
    categories: [Computer Science]
    modules:
      - org.scala-graph:graph-core
```

This expands `graph-core` into `graph-core_2.13` and `graph-core_3`. Expand all configured modules, check published JVM Scala 2.13/3 coordinates, then select at most 50 by `dependent_packages_count` descending. Known counts (including zero) precede unknown counts; ties use coordinate name. Projects with fifty or fewer published candidates keep all candidates without a ranking-metadata request. The YAML records `max_artifacts_per_project: 50` and the ranking rule. The SQLite `artifact_selection` table records each published candidate, its count (nullable), rank, selected flag, metadata source and reason. Raw metadata pages remain in evidence. Unknown counts generate selection gaps when ranking is needed. External coordinates cannot bridge paths.

Select all eligible projects across all 76 Awesome Scala subsections, traversing every listing page and deduplicating repositories. There is no project or subsection quota. Eligibility still requires published coordinates in the configured matrix, latest-release evidence and Scala as the largest source language. Ordinary rebuilds preserve the frozen seed.

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

## Scalaland storytelling map

Generate a separate, standalone interactive atlas from the latest analyzed snapshot:

```sh
./scripts/render-map.sh
```

Open `output/ecosystem-map.html` directly in a browser. It includes score layers,
pan/zoom, project search, hover connections with a hop filter, and multi-project
compromise scenarios. It does not replace `preview.html` or change collection.

The first run generates an Azgaar world; later runs reuse `output/map/world.json`
and refresh the data without running the generator. Use `--database <snapshot>`
for specific data, or `--regenerate-world --map-seed <number>` to explicitly create
new geography. A changed project roster requires explicit regeneration.

First-world generation requires Node.js 24+, npm and the existing Playwright
Chromium setup; generator dependencies are downloaded and cached once. Refreshes
and the delivered HTML work offline. See [MAP-PILOT.md](docs/MAP-PILOT.md) for setup,
architecture, visual decisions, simulation semantics and performance measurements.

## Layout

- `src/scala_security/`: collection, typed model boundaries, SQLite schema, analysis, rendering and CLI.
- `src/scala_security/templates/`: self-contained report template with native MathML formulas.
- `tests/`: graph, scores, HTTP/cache, selection, integration and browser regressions.
- `scripts/`: rebuild and validation entry points.
- `config/`: reviewed seed configuration and selection provenance.
- `docs/`: [methodology](docs/METHODOLOGY.md), implementation tasks and supporting notes.
- `model/`, `data/`: original vision documents and partner-supplied inputs.
- `output/`: ignored generated results and evidence.

Website deployment is out of scope. The GitHub repository is private; CI validates the code and does not publish the report.

## Publish the reviewed report

The public site is https://anatoliikmt.me/scala-ecosystem-security-model/.
It inherits the account website's custom domain; the account website remains unchanged.

After generating and reviewing `output/preview.html`, run:

```sh
./scripts/publish.sh
```

The script must run on `main` with no pre-existing staged changes. It copies the
reviewed report to `site/index.html`, commits the publication files and pushes
`main`. GitHub Actions then deploys only `site/` to GitHub Pages. No collection,
Python runtime, database or evidence cache is deployed. An optional first argument
selects a different reviewed HTML file. Track deployment with
`gh run list --workflow publish.yml`.

Source changes alone do not republish the report. Regenerate, review and invoke
the publishing script when the report should change. The workflow also supports
manual dispatch to redeploy the already committed report. To roll back, restore
the desired earlier `site/index.html`, commit it and push `main`.
