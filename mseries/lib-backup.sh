# shellcheck shell=bash
# Source this from the install-*.sh scripts that replace a file owned by an apt
# package with a patched build.
#
#   mseries_backup  FILE PACKAGE   save the packaged FILE before it is replaced
#   mseries_restore FILE PACKAGE   put the packaged FILE back
#   mseries_install_indicator MODE SRC DEST   replace a Wingpanel indicator without a temp file in its directory
#
# Why not just keep one "*.original": a package upgrade rewrites FILE with the
# new version, but an old backup still holds the previous one. Restoring that
# over the new package puts a binary built against other library versions in
# place. The backup therefore records the package version it came from; a
# restore with a different installed version reinstalls the package instead.

_mseries_backup_path() { printf '%s/%s.original' "${MSERIES_BACKUP_DIR:-/usr/local/lib/mseries}" "$(basename "$1")"; }

mseries_backup() {
  local file=$1 pkg=$2 backup version
  backup=$(_mseries_backup_path "$file")
  version=$(dpkg-query -W -f='${Version}' "$pkg")
  # A backup from before versions were recorded: FILE is probably already our
  # patched build, so overwriting the backup with it would lose the original for
  # good. Keep it; restore will not trust it (no matching version) and
  # reinstalls the package instead.
  if [[ -f $backup && ! -f $backup.version ]]; then
    return 0
  fi
  # Same version already saved: FILE may be our patched build, keep the backup.
  if [[ -f $backup && $(cat "$backup.version" 2>/dev/null || true) == "$version" ]]; then
    return 0
  fi
  # No backup, or one from another version: FILE is the package's own, because
  # the upgrade that changed the version also replaced the patched file.
  sudo install -D -m "$(stat -c %a "$file")" "$file" "$backup"
  printf '%s\n' "$version" | sudo tee "$backup.version" >/dev/null
}

mseries_restore() {
  local file=$1 pkg=$2 backup version
  backup=$(_mseries_backup_path "$file")
  version=$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || true)
  if [[ -f $backup && $(cat "$backup.version" 2>/dev/null || true) == "$version" ]]; then
    sudo install -m "$(stat -c %a "$file")" "$backup" "$file"
  else
    echo "No saved original for $pkg ${version:-?}; reinstalling the package to restore $file." >&2
    sudo apt-get install --reinstall -y "$pkg"
  fi
}

# Wingpanel watches its indicators directory and loads anything containing
# ".so", including a "*.so.new" temp file (that crashed it at 09:19 on 2026-10-26).
# Stage in a sibling directory on the same filesystem, then rename: the running
# panel sees one complete file appear and never a partial or duplicate module.
mseries_install_indicator() {
  local mode=$1 src=$2 dest=$3 dir stage tmp
  dir=$(dirname "$dest")
  stage="$dir/../mseries-pending-indicators"
  sudo install -d -m 0755 "$stage"
  if [[ $(stat -c %d "$dir") != "$(stat -c %d "$stage")" ]]; then
    echo "Refusing to stage $dest: $stage is on another filesystem, so the rename would not be atomic." >&2
    return 1
  fi
  tmp="$stage/$(basename "$dest").$$.staging"
  sudo install -m "$mode" "$src" "$tmp"
  sudo mv -f "$tmp" "$dest"
}
