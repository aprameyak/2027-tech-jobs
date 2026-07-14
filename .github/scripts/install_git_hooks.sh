#!/bin/sh
set -eu
ROOT=$(git rev-parse --show-toplevel)
mkdir -p "$ROOT/.git/hooks"
install -m 755 "$ROOT/.github/hooks/prepare-commit-msg" "$ROOT/.git/hooks/prepare-commit-msg"
echo "Installed prepare-commit-msg hook (strips Cursor co-author trailers)."
