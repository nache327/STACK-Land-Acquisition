#!/usr/bin/env bash
# install-hygiene-hooks.sh — wire scripts/lane-check.sh as the local
# pre-commit hook. Per-clone, one-time setup. Safe to re-run.
#
# Idempotent. Backs up any existing pre-commit hook to pre-commit.bak.

set -eu

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

hook_path=".git/hooks/pre-commit"
check_path="scripts/lane-check.sh"

[ -f "$check_path" ] || { echo "✗ $check_path not found"; exit 1; }
chmod +x "$check_path"

if [ -e "$hook_path" ] && [ ! -L "$hook_path" ]; then
  # existing real file — back it up
  cp "$hook_path" "$hook_path.bak"
  echo "ℹ backed up existing $hook_path → $hook_path.bak"
fi

ln -sf "../../$check_path" "$hook_path"
chmod +x "$hook_path" 2>/dev/null || true
echo "✓ pre-commit hook installed: $hook_path → $check_path"
echo "  (warn-only; never blocks a commit)"
