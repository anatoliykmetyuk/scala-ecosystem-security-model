# Scala ecosystem security model

Project foundation uses Python 3.13, uv, Ruff, ty and pytest.

Install uv, then run `uv sync --locked` and `./scripts/check.sh`.

Implementation requirements: [task list](docs/TASKS.md).
Source material remains in `model/` and partner input in `data/`.
Generated pilot artifacts are ignored by Git.
