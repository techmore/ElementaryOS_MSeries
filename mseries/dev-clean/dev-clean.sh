#!/usr/bin/env bash
# Weekly developer cleanup for this Mac. Everything it removes is regenerable or already in the way:
# Rust build output, build caches, Claude session scratch in RAM-backed /tmp, old dated Codex
# export folders (sent to the Trash, not deleted), container leftovers, stale git worktree records,
# journal and apt caches. The owner's own files (Documents, vms, repos) are never touched.
#
#   dev-clean            run it
#   dev-clean --dry-run  print what would go, remove nothing
#
# Installed by mseries/dev-clean/install.sh as ~/.local/bin/dev-clean with a weekly user timer;
# the log of the last run is ~/.cache/dev-clean/last.log. Rules: mseries/DEV-HYGIENE.md.
set -u
DRY=${1:-}
H=$HOME
LOG_DIR=$H/.cache/dev-clean
mkdir -p "$LOG_DIR"
say() { printf '%s\n' "$*"; }
run() {
  if [ "$DRY" = "--dry-run" ]; then say "  would: $*"; else "$@"; fi
}

say "== dev-clean $(date '+%F %T') ${DRY:+(dry run)} =="
say "== disk before =="; df -h / | tail -1

say "== rust build output =="
# Stray per-worktree target dirs: ~/.cargo/config.toml points every build at one shared dir, so a
# rust/target inside a checkout means something overrode target-dir.
find "$H/Projects" "$H/claude-work" "$H/src" "$H"/ElementaryOS_MSeries* -maxdepth 6 -type d -name target -path '*rust*' -prune 2>/dev/null |
  while read -r t; do run rm -rf "$t"; done
# The shared target dir: drop it after 7 days without a build; cargo rebuilds the dependencies once.
if [ -d "$H/.cache/cargo-target" ] && [ -z "$(find "$H/.cache/cargo-target" -maxdepth 0 -mtime -7)" ]; then
  run rm -rf "$H/.cache/cargo-target"
fi

# Inside the shared target dir rustc keeps one incremental folder per build configuration, so a crate that was
# built with different flags or features many times leaves dozens (measured 2026-10-23: 235 folders, 3.4 GB, 276 MB
# after keeping the newest per crate). Only the newest per crate is ever reused, so the rest goes at no rebuild cost.
inc="$H/.cache/cargo-target/debug/incremental"
if [ -d "$inc" ]; then
  python3 - "$inc" "$DRY" <<'PY'
import os, re, shutil, sys, collections
root, dry = sys.argv[1], sys.argv[2] == "--dry-run"
groups = collections.defaultdict(list)
for d in os.listdir(root):
    m = re.match(r"^(.*)-[a-z0-9]+$", d)
    if m and os.path.isdir(os.path.join(root, d)):
        groups[m.group(1)].append((os.path.getmtime(os.path.join(root, d)), d))
stale = [d for items in groups.values() for _, d in sorted(items, reverse=True)[1:]]
for d in stale:
    if not dry:
        shutil.rmtree(os.path.join(root, d), ignore_errors=True)
print(f"  {'would remove' if dry else 'removed'} {len(stale)} stale incremental folders ({len(groups)} crates keep their newest)")
PY
fi

say "== node_modules outside active repos =="
find "$H/src" "$H/claude-work" -maxdepth 4 -type d -name node_modules -prune 2>/dev/null |
  while read -r n; do run rm -rf "$n"; done

say "== caches =="
for c in mseries-build mseries-diskspace-target ms-playwright tracker3 electron pip golangci-lint mesa_shader_cache; do
  [ -d "$H/.cache/$c" ] && run rm -rf "$H/.cache/$c"
done
find "$H/.cache" -maxdepth 1 -type d \( -name 'omarchy-mlx-*' -o -name '*-venv' \) 2>/dev/null |
  while read -r d; do run rm -rf "$d"; done

say "== claude session scratch in RAM-backed /tmp (older than 2 days) =="
find /tmp/claude-1000 -mindepth 2 -maxdepth 2 -type d -mtime +2 2>/dev/null |
  while read -r d; do run rm -rf "$d"; done
find /tmp/claude-1000 -maxdepth 1 -type f -name 'cache-break-state-*' -mtime +2 2>/dev/null |
  while read -r f; do run rm -f "$f"; done

say "== Documents/Codex dated export folders (older than 3 days, to the Trash) =="
# Only folders whose name carries a date (2026-10-21 or name-20261021) and that are older than
# three days; they go to the Trash with gio, so a wanted one can be put back from Files.
if [ -d "$H/Documents/Codex" ]; then
  find "$H/Documents/Codex" -mindepth 1 -maxdepth 1 -type d -mtime +3 2>/dev/null | while read -r d; do
    base=$(basename "$d")
    case "$base" in
      [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]* | *-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) run gio trash "$d" ;;
      *) say "  kept (no date in the name): $base" ;;
    esac
  done
fi

say "== containers =="
if command -v podman >/dev/null 2>&1; then run podman system prune -f --volumes; fi

say "== git worktrees =="
# Every repo under ~/Projects plus the two main checkouts: prune records of worktrees whose
# directories are gone (retiring merged worktrees stays a manual pass, see mseries/REPO-HYGIENE.md).
for repo in "$H"/Projects/*/ "$H/ElementaryOS_MSeries"; do
  [ -e "$repo/.git" ] || continue
  main=$(git -C "$repo" worktree list 2>/dev/null | head -1 | awk '{print $1}')
  [ "$main" = "${repo%/}" ] || continue   # a worktree, not the main checkout
  run git -C "$repo" worktree prune
  say "  worktrees in $repo: $(git -C "$repo" worktree list 2>/dev/null | wc -l)"
done

say "== system =="
run journalctl --vacuum-size=100M
if sudo -n true 2>/dev/null; then run sudo -n apt-get clean; else say "  apt-get clean skipped (needs sudo)"; fi
if command -v flatpak >/dev/null 2>&1; then run flatpak uninstall --unused -y --noninteractive; fi

say "== disk after =="; df -h / | tail -1
say "== memory =="; free -h | sed -n '2,3p'
