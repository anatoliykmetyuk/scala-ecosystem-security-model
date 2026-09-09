#!/usr/bin/env bash
# Publish the locally reviewed website; never starts data collection.
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
website="${1:-output}"
pages=(index.html preview.html ecosystem-map.html)
# Validate the entire website before changing any publication files.
for page in "${pages[@]}"; do
  if [[ ! -s "$website/$page" ]]; then
    echo "Page not found: $website/$page. Generate and review the website first." >&2
    exit 1
  fi
done
mkdir -p site
for page in "${pages[@]}"; do
  cp "$website/$page" "site/$page"
done
touch site/.nojekyll
git add site/index.html site/preview.html site/ecosystem-map.html site/.nojekyll
if git diff --cached --quiet; then
  echo "Published website is unchanged."
else
  git commit -m "Publish reviewed Scala Land website"
fi
git push origin main
echo "GitHub Actions deploys the homepage, rankings, and atlas from site/. Check: gh run list --workflow publish.yml"
