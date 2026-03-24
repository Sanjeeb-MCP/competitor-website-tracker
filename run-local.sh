#!/bin/bash
# Runs the tracker locally for blocked competitors (advantageclub.ai)
# Then commits and pushes changes to GitHub

cd "$(dirname "$0")"

echo "$(date): Starting local crawl for Advantage Club..."

# Run tracker with local-only config
python3 -m tracker.main --config config/local-only.yml --verbose

# Check if there are changes to push
if ! git diff --quiet data/ docs/; then
  echo "$(date): Changes detected, pushing to GitHub..."
  git add data/ docs/
  git commit -m "chore: local crawl update - Advantage Club [$(date -u +%Y-%m-%dT%H:%M:%SZ)]"
  git pull --rebase origin main
  git push origin main
  echo "$(date): Pushed successfully."
else
  echo "$(date): No changes detected."
fi

echo "$(date): Done."
