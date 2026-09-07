# Scala ecosystem security model

A reproducible assessment of a frozen, curated Scala cohort. It ranks projects with low observed maintenance or security scores by the summed Value of their verified Maven dependants, up to three dependency hops. Java projects may contribute downstream Value but are not assessment subjects.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from this repository:

```sh
uv python install 3.13
uv sync --locked
uv run playwright install chromium
```

On Linux, browser tests may require `uv run playwright install --with-deps chromium`.
Optional: sign into `gh auth login` to use authenticated public GitHub metadata requests during seed selection. Credentials are never stored in evidence or generated output. The normal rebuild uses the already-frozen seed configuration.

## Rebuild from scratch

```sh
./scripts/rebuild.sh
```

This single command reads **[config/seeds.yaml](config/seeds.yaml)**, creates a fresh evidence directory and SQLite snapshot, collects dependencies and score inputs, calculates and validates results, then generates **`output/preview.html`**. Open that file directly in a browser. It embeds the required data and needs no API connection or local server to view.

This is a substantial Maven-wide crawl, not a quick build: every artifact variant of the selected projects is queried, followed by reverse discovery through three hops and version-specific verification. Runtime depends on index size and API response times. Progress is printed by phase and batch. HTTP failures and unresolved declarations are recorded as gaps, not silently converted to zero scores. The preview reports the gap count.

Each run is retained under `output/runs/<UTC timestamp>/`:

- `seeds.yaml`: exact input used for this run.
- `snapshot.sqlite`: normalized collected entities, observations, calculated scores, fallout paths, rankings, gaps and request provenance.
- `evidence/`: URL-addressed gzip-compressed HTTP responses, unless explicitly reusing another directory.
- `validation.json`: verified table/path counts.

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

The editable YAML records repositories, categories, source ranks/URLs, Scala eligibility evidence, artifact inventories and exclusions. The current selection takes up to ten eligible projects per Awesome Scala category in Scaladex's default order. The cohort is fixed across ordinary rebuilds; artifact coverage is refreshed for those projects.

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
