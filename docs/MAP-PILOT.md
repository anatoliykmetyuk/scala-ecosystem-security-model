# Scalaland map pilot

The map is a storytelling companion to the evidence report. The original collection,
analysis, `preview.html`, and publication workflow are unchanged. No map is published
automatically.

## Generate or refresh

From the repository root:

```sh
./scripts/render-map.sh
```

This reads `output/latest-database.txt`, opens that SQLite snapshot **read-only**, and
writes `output/ecosystem-map.html`. Open that HTML directly in a browser or share the
file. It needs no server, network connection, CDN, fonts, or accompanying files.

Specify an existing analyzed snapshot explicitly:

```sh
./scripts/render-map.sh --database output/runs/<snapshot>/snapshot.sqlite
```

The equivalent CLI is `uv run scala-security render-map`. `--output` specifies a
directory; the HTML filename is `ecosystem-map.html`. All shell-wrapper paths are
resolved relative to the repository root, consistent with the other scripts.

The first run generates and saves `output/map/world.json`. Subsequent runs reuse
the project-to-country assignment and geometry, updating only the data and viewer.
Retain that JSON alongside your data if you want to preserve the geography across
machines. No generator or browser runtime is needed to refresh an existing world.

A changed project roster is reported explicitly; it never silently drops new
projects or remaps the current world. Generate a replacement deliberately:

```sh
./scripts/render-map.sh --regenerate-world --map-seed 20260908
```

Use `--world path/to/world.json` to maintain alternative saved worlds. Back up an
existing world if you want to retain it when explicitly regenerating. Failed
generation or roster validation preserves the previous map and world. The same
snapshot, world, and renderer produce byte-identical HTML.

## First-world requirements

The normal repository setup already installs Python Playwright through the dev
dependency group. Creating new geography additionally needs **Node.js 24+**, npm,
and the Playwright Chromium runtime:

```sh
uv sync --locked
uv run playwright install chromium
```

On the first world build, the adapter downloads an Azgaar source archive pinned to
`f30ffd812e391f9f979d5a3c54be99e2b4920b64` (v1.110.0), verifies its SHA-256, and runs
`npm ci --ignore-scripts` and Vite using Azgaar's package lock. Downloaded source and
build dependencies stay in `.cache/azgaar/`; `--generator-cache` overrides this path.
Bootstrap needs network access to GitHub and npm. Reusing the cached generator does
not. Generation runs in a disposable headless Chromium context served from a
temporary localhost server. All non-local browser requests are blocked; no snapshot
data is sent to Azgaar or another remote service.

The browser is used as the generator's build runtime because this Azgaar release
uses browser globals. It is not embedded in the deliverable. This avoids shipping
the editor, generator, geopolitical simulation, or fine-grained cell data.

## Structure

```text
snapshot.sqlite (read-only)
  + saved world.json (generated only on request)
  + map.html / map.css / map.js
  -> ecosystem-map.html
```

- `map_world.py`: pinned generator bootstrap and build runtime.
- `map_generate.js`: small adapter around the pinned Azgaar generation/export functions.
- `map_render.py`: snapshot export, roster validation, country binding and HTML assembly.
- `templates/map.*`: independent viewer assets, inlined at build time.
- `scripts/check-map.py`: offline full-dataset smoke test and measurement report.

## Visual decisions

The supplied 2023 Scalaland poster guides the geography's flat vector illustrations,
teal land/water palette, forest and mountain symbols, and nautical details. The Scala
Center Five-Year Impact Report screenshots guide orange/peach data accents, pale
type, large impact numerals and restrained rules. These are visual references;
terrain, islands, proximity and regions have no dependency or scoring meaning.

The pilot generates an organic distribution of country sizes and assigns projects
by star rank, largest first. This adopts the geography-first option discussed during
research. It does **not** claim square-root-proportional areas: square-root stars
have the same rank as raw stars, and natural country sizes are retained. Unknown
stars sort with zero after known positive values; repository ID breaks ties. On
refresh, changing stars does not move or resize countries. Some countries are small
and require zoom or search. Labels progressively appear as space permits; search
provides access to every project, including countries whose full names do not fit.

Default color is Exposed Value. Its color intensity uses square-root scaling to
keep moderate exposure visible; the legend marks actual values at the ends and
midpoint. Project Value uses its existing 0–1 score. Maintenance and Security use
0–1 scales with warmer colors for lower scores. Unknown scores are hatched.

Country area and color are separate. Compromised countries use red plus diagonal
hatching; exposed dependants use a peach tint and outline. This keeps simulation
status distinguishable from the current score layer.

## Simulation semantics

- Click a country to compromise it; click it again or its chip to undo. Search
  inspects and centers a country without compromising it; a separate button acts.
- The simulation uses the saved, verified `fallout` sets. It never transitively
  closes repository-level links, which would lose historical version semantics.
- Multiple selections use set union. A directly compromised project that is also
  someone else's dependant counts as compromised, not twice.
- Affected project percentage includes both compromised and exposed projects,
  divided by all scored seed projects in the map.
- Affected Value percentage sums known Values of affected projects and divides by
  known Value across the mapped cohort. Unknown Values are counted separately.
- Simulation uses all retained paths, up to five hops. The connection-depth slider
  filters hover lines only. Lines run from the hovered project to its verified
  dependants within the selected depth, rather than pretending to be a complete
  drawing of all intermediate artifact edges.
- Reset clears every compromise. It does not alter scores or the saved snapshot.

This is a scenario about potential downstream exposure, not a prediction of actual
exploitability or infection probability. Seed-only coverage, JVM Scala 2.13/3,
selected-artifact limits, and evidence gaps remain the same as the original report.

## Verification and measurements

```sh
./scripts/check.sh
uv run python scripts/check-map.py output/ecosystem-map.html
```

The regular offline suite checks historical-version correctness, union counting,
unknown scores/Values, keyboard search, layer changes, reset, responsive overflow,
read-only snapshots, stable saved-world refreshes, and roster-change protection.
It uses a small fixture and does not download or generate Azgaar maps in CI.

The full-data smoke test runs the HTML from `file://` in offline Chromium, checks
multi-country counts against its exported data, filters hover links, verifies that
dragging does not compromise a country, and saves screenshots plus timings under
`output/map-verification/`. These timings include automation overhead and are not
frame-rate benchmarks or guarantees for other browsers/devices.

Initial measured full dataset, 2026-09-08:

| Measure | Result |
| --- | --- |
| Snapshot | `20260908T072758329207Z` |
| Projects / relationships | 548 / 3,648 |
| Standalone HTML | approximately 1.37 MB |
| Cached generator startup + world generation/export | approximately 4.5 s |
| Refresh saved geography | approximately 0.03 s |
| Offline Chromium load through map-ready | approximately 0.09 s |
| Compromise actions | approximately 0.03–0.05 s |
| Layer actions | approximately 0.005–0.022 s |
| External viewer requests / JavaScript errors | 0 / 0 |
| Same seed generated twice | identical exported world |

The geometry has 548 country paths; the exported world includes 47 land features,
53 lakes, 490 rivers and 1,572 lightweight scenery symbols. Detail is bounded and
uses reusable SVG symbols. The full generator's cell mesh and editor are absent.

Larger cohorts have not been benchmarked. The adapter currently requests 60,000
initial grid cells and verifies that every requested country was generated. If
Azgaar cannot place all capitals, it fails instead of dropping projects.

## References

- [Azgaar](https://github.com/Azgaar/Fantasy-Map-Generator), pinned MIT-licensed source; notice embedded in the HTML.
- [Red Blob Games](https://www.redblobgames.com/maps/mapgen2/), terrain generation and illustrated maps.
- [Uncharted Atlas](https://github.com/mewo2/terrain), procedural fantasy cartography.
- [Here Dragons Abound](https://heredragonsabound.blogspot.com/), illustrated terrain and label placement.
- [Scala Center report](https://scala.epfl.ch/records/first-five-years/report), supplied screenshot reference.
