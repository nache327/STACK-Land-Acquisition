#!/usr/bin/env bash
# lane-check.sh — warn-only lane hygiene check.
#
# Reads HOT_FILES (in repo root) and warns when the current staged diff:
#   - touches files marked as hot
#   - touches more than one hot file in a single commit
#   - touches a migration without a claim in MIGRATION_RESERVATIONS.md
#   - is on `main` directly (skip the lane workflow)
#
# Designed to run as a pre-commit hook (see scripts/install-hygiene-hooks.sh)
# or invoked manually before commit. Never blocks — only prints.

set -u

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$repo_root" || exit 0

hot_file="$repo_root/HOT_FILES"
mig_file="$repo_root/MIGRATION_RESERVATIONS.md"

# Branch check
branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")
if [ "$branch" = "main" ]; then
  echo "⚠ lane-check: committing directly to main — feature work belongs on a feat/* or fix/* branch"
fi

# Collect staged paths (skip the rest if nothing staged — common when invoked manually)
staged=$(git diff --cached --name-only 2>/dev/null)
[ -z "$staged" ] && exit 0

# Hot-file overlap
if [ -f "$hot_file" ]; then
  # Filter HOT_FILES to non-empty, non-comment lines; match as fixed-string prefix
  patterns=$(grep -v '^[[:space:]]*#' "$hot_file" | grep -v '^[[:space:]]*$')
  hot_hits=""
  while IFS= read -r pat; do
    [ -z "$pat" ] && continue
    matches=$(echo "$staged" | grep -F "$pat" || true)
    [ -n "$matches" ] && hot_hits="$hot_hits$matches"$'\n'
  done <<< "$patterns"
  hot_hits=$(echo "$hot_hits" | grep -v '^$' | sort -u)
  hot_count=$(echo "$hot_hits" | grep -c . || true)
  if [ "$hot_count" -gt 0 ]; then
    echo "⚠ lane-check: commit touches $hot_count hot file(s):"
    echo "$hot_hits" | sed 's/^/    /'
    if [ "$hot_count" -gt 1 ]; then
      echo "  consider splitting this commit per lane (Slot 1 is serial)."
    fi
  fi
fi

# Migration claim check
mig_lines=$(echo "$staged" | grep '^backend/alembic/versions/.*\.py$' || true)
if [ -n "$mig_lines" ]; then
  echo "⚠ lane-check: this commit adds/edits alembic migrations:"
  echo "$mig_lines" | sed 's/^/    /'
  if [ -f "$mig_file" ]; then
    # Extract migration number(s) from filename(s)
    for f in $mig_lines; do
      num=$(basename "$f" | grep -oE '^[0-9]{4}' || true)
      [ -z "$num" ] && continue
      if ! grep -q "^| $num " "$mig_file"; then
        echo "  migration $num has NO claim in MIGRATION_RESERVATIONS.md — add a row before merging."
      fi
    done
  fi
fi

exit 0
