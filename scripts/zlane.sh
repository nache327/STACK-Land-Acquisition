# zlane.sh — shell helpers for spawning/cleaning/verifying lane worktrees.
#
# Source from ~/.zshrc or ~/.bashrc:
#   export ZONING_REPO=$HOME/Desktop/STACK_land_acquisition/STACK-Land-Acquisition
#   source $ZONING_REPO/scripts/zlane.sh
#
# Then:
#   zlane <slug> <branch>      # spawn worktree off latest origin/main
#   zlane-done <slug>          # remove worktree after merge/abandon
#   zready                     # pre-merge gate (run from integration checkout)
#   zverify [sha12]            # poll /health until deployed SHA matches

: "${ZONING_REPO:=$HOME/Desktop/STACK_land_acquisition/STACK-Land-Acquisition}"
: "${ZONING_WT_ROOT:=$HOME/work/zoning-wt}"
: "${ZONING_API:=https://capable-serenity-production-0d1a.up.railway.app}"

zlane() {
  local slug=${1:-}
  local branch=${2:-}
  if [ -z "$slug" ] || [ -z "$branch" ]; then
    echo "usage: zlane <slug> <type/branch-name>   e.g.  zlane marlboro-fix fix/coverage-refresh-stale-session"
    return 1
  fi
  mkdir -p "$ZONING_WT_ROOT"
  local wt="$ZONING_WT_ROOT/wt-$slug"
  if [ -d "$wt" ]; then
    echo "✗ worktree already exists at $wt — use zlane-done $slug first"
    return 1
  fi
  ( cd "$ZONING_REPO" && git fetch origin --quiet \
    && git worktree add "$wt" -b "$branch" origin/main ) || return $?
  cd "$wt" || return $?
  echo "✓ worktree ready: $wt on $branch"
  echo "  next: claude  (start in plan mode for non-trivial work)"
}

zlane-done() {
  local slug=${1:-}
  if [ -z "$slug" ]; then
    echo "usage: zlane-done <slug>"
    return 1
  fi
  local wt="$ZONING_WT_ROOT/wt-$slug"
  ( cd "$ZONING_REPO" && \
    ( git worktree remove "$wt" 2>/dev/null \
      || git worktree remove --force "$wt" ) \
    && echo "✓ worktree removed: $wt" )
}

zready() {
  ( cd "$ZONING_REPO" && \
    echo "=== local main vs origin/main (want 0  0) ===" && \
    git fetch origin --quiet && \
    git rev-list --left-right --count main...origin/main && \
    echo "=== /health (deployed SHA) ===" && \
    curl -sS -m 5 "$ZONING_API/health" && echo && \
    echo "=== alembic-status (db_head should == disk head) ===" && \
    curl -sS -m 5 "$ZONING_API/api/debug/alembic-status" && echo && \
    echo "=== stale jobs (want []) ===" && \
    curl -sS -m 5 "$ZONING_API/api/admin/jobs?stale_only=true&limit=20" && echo )
}

zverify() {
  local target=${1:-$(cd "$ZONING_REPO" && git rev-parse origin/main | cut -c1-12)}
  echo "verifying deploy of $target ..."
  local i
  for i in $(seq 1 20); do
    local cur=$(curl -sS -m 5 "$ZONING_API/health" 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin)["pipeline_version"])' 2>/dev/null)
    if [ "$cur" = "$target" ]; then
      echo "✓ deployed $cur"
      return 0
    fi
    echo "  pipeline_version=$cur  (waiting for $target — attempt $i/20)"
    sleep 45
  done
  echo "✗ deploy never matched $target after 15 min — investigate Railway"
  return 1
}
