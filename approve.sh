#!/bin/bash
# Usage: ./approve.sh 123 124 125
# Labels each issue as "approved", which triggers the add-listing workflow
# to automatically add it to listings.json and README.md.
#
# Requires GITHUB_TOKEN env var or gh CLI to be authenticated.

set -e

REPO="aprameyak/2027-swe-jobs"

if [ $# -eq 0 ]; then
  echo "Usage: $0 <issue_number> [issue_number ...]"
  exit 1
fi

for ISSUE in "$@"; do
  gh issue edit "$ISSUE" --repo "$REPO" --add-label "approved"
  echo "✅ #$ISSUE approved"
done

echo "Done — add-listing workflow will process these automatically."
