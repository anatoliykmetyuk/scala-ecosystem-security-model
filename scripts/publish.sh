#!/usr/bin/env bash
# Publish the locally reviewed report; never starts data collection.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Publish from main." >&2
  exit 1
fi
if ! git diff --cached --quiet; then
  echo "Commit or unstage existing staged changes before publishing." >&2
  exit 1
fi
report="${1:-output/preview.html}"
if [[ ! -s "$report" ]]; then
  echo "Report not found: $report. Generate and review it first." >&2
  exit 1
fi
mkdir -p site
cp "$report" site/index.html
 touch site/.nojekyll
 git add site/index.html site/.nojekyll
if git diff --cached --quiet; then
  echo "Published report is unchanged."
else
  git commit -m "Publish reviewed ecosystem report"
fi
 git push origin main
 echo "GitHub Actions deploys site/index.html. Check: gh run list --workflow publish.yml"
