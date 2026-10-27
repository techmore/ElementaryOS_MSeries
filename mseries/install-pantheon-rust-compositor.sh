#!/usr/bin/env bash
# Install the experimental Pantheon Rust compositor onto the existing elementary OS
# M-series stack, next to Gala — never over it.
#
#   bash mseries/install-pantheon-rust-compositor.sh --dry-run      # default: checks only, changes nothing
#   bash mseries/install-pantheon-rust-compositor.sh --status       # installed-vs-loaded state, changes nothing
#   bash mseries/install-pantheon-rust-compositor.sh --verify       # read-only integrity checks
#   sudo bash mseries/install-pantheon-rust-compositor.sh --install --yes --deb /path/to/pantheon-rust-compositor_*_arm64.deb
#   sudo bash mseries/install-pantheon-rust-compositor.sh --install --yes --build
#   sudo bash mseries/install-pantheon-rust-compositor.sh --select --yes     # next login uses the Rust session
#   sudo bash mseries/install-pantheon-rust-compositor.sh --restore-gala --yes
#   sudo bash mseries/install-pantheon-rust-compositor.sh --uninstall --yes
#
# SAFETY DESIGN
#  * The compositor ships as its own Debian package and its own LightDM session,
#    "Pantheon (Rust compositor, experimental)". The Gala session entry, the Gala
#    package and /usr/bin/gala are never modified. Gala stays the rollback path.
#  * Dry run is the default. --install, --select, --restore-gala and --uninstall
#    act, need root and need --yes; each prints the exact rollback command.
#  * The running session is never switched, restarted or logged out. Installing a
#    newer package does not touch the active compositor; the Rust session only
#    takes effect at the next login, like the Gala screen-corner patches.
#  * The installer starts and enables nothing. After dpkg it only runs
#    `systemctl --user daemon-reload` so the staged units are known without
#    starting them (the units carry RefuseManualStart=on anyway).
#  * --select only rewrites the LightDM autologin drop-in, after saving a backup.
#    It arms no timer and logs nobody out.
#
# This installs an experimental compositor. It has NOT been qualified to replace
# Gala: read mseries/pantheon-rust-compositor/README.md and
# docs/rust-compositor-performance.html before selecting the Rust session.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
component=$repo/mseries/pantheon-rust-compositor
session_name=pantheon-rust-wayland
gala_session=pantheon-wayland
compositor_template=pantheon-rust-compositor@.service
compositor_unit=pantheon-rust-compositor@wayland.service
autologin_dropin=/etc/lightdm/lightdm.conf.d/50-elementary-mac-autologin.conf
deb_path=
build=0
action=dry-run
confirm=0

usage() {
  awk 'NR > 1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0" >&2
  exit 2
}

log() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# Privileged commands are printed in read-only modes and executed otherwise.
as_root() {
  case $action in
    dry-run|status|verify)
      log "  would run: sudo $*"
      return 0 ;;
  esac
  sudo "$@"
}

# Always address the invoking desktop owner, including when invoked through sudo.
user_systemctl() {
  if (( EUID != 0 )); then
    systemctl --user "$@"
    return
  fi
  local owner=${SUDO_USER:-} uid runtime
  [[ -n $owner && $owner != root ]] || return 1
  uid=$(id -u -- "$owner") || return 1
  runtime=/run/user/$uid
  [[ -S $runtime/bus ]] || return 1
  runuser -u "$owner" -- env XDG_RUNTIME_DIR="$runtime" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" systemctl --user "$@"
}

reload_user_manager() {
  if user_systemctl daemon-reload; then
    log "desktop owner's user manager reloaded; no services restarted"
  else
    warn "package operation succeeded; desktop owner's user manager is unavailable. Units load at the next login."
  fi
}

need_yes() {
  [[ $confirm == 1 ]] || die "refusing to act without --yes (read the safety design above)"
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) action=dry-run ;;
    --status|--verify|--install|--uninstall|--select|--restore-gala) action=${1#--} ;;
    --build) build=1 ;;
    --deb) deb_path=${2:?--deb needs a package path}; shift ;;
    --yes) confirm=1 ;;
    -h|--help) usage ;;
    *) echo "Unknown option $1" >&2; usage ;;
  esac
  shift
done

# ---------------------------------------------------------------- preflight

[[ $(dpkg --print-architecture) == arm64 ]] \
  || die "this native compositor package is for arm64; host is $(dpkg --print-architecture)"

step "Existing stack (the rollback path)"
gala_version=$(dpkg-query -W -f='${Version}' gala 2>/dev/null || true)
[[ -n $gala_version ]] || die "the gala package is not installed; there is no rollback path"
[[ -x /usr/bin/gala ]] || die "/usr/bin/gala is missing; there is no rollback path"
[[ -f /usr/share/wayland-sessions/$gala_session.desktop ]] \
  || die "the $gala_session session entry is missing; there is no rollback path"
log "gala $gala_version, /usr/bin/gala and the $gala_session session entry are intact"

for dep in io.elementary.wingpanel io.elementary.dock gnome-session gtklock \
           xdg-desktop-portal xwayland; do
  version=$(dpkg-query -W -f='${Version}' "$dep" 2>/dev/null || true)
  [[ -n $version ]] || die "missing dependency $dep (sudo apt install $dep)"
  log "dependency $dep $version"
done

# Where LightDM's autologin session comes from today. Drop-ins are read in
# lexical order after the main config, so the last match wins.
autologin_sources=()
for conf in /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.d/*.conf; do
  [[ -f $conf ]] || continue
  grep -q '^[[:space:]]*autologin-session=' "$conf" && autologin_sources+=("$conf")
done
autologin_session=
for conf in "${autologin_sources[@]:-}"; do
  [[ -n $conf ]] || continue
  value=$(sed -n 's/^[[:space:]]*autologin-session=[[:space:]]*//p' "$conf" | tail -1)
  [[ -n $value ]] && autologin_session=$value
done
if (( ${#autologin_sources[@]} > 1 )); then
  warn "autologin-session is set in several files: ${autologin_sources[*]}"
  warn "this script writes $autologin_dropin; lexical order decides the winner"
fi
log "LightDM autologin: ${autologin_session:-<unset>}"

step "Current Rust compositor state (installed vs loaded)"
installed_version=$(dpkg-query -W -f='${Version}' pantheon-rust-compositor 2>/dev/null || true)
log "package: ${installed_version:-<not installed>}"
if [[ -n $installed_version ]]; then
  if verify_output=$(dpkg -V pantheon-rust-compositor 2>&1); then
    log "dpkg -V: no modified or missing files"
  else
    log "dpkg -V reported differences:"
    printf '%s\n' "$verify_output" | sed 's/^/  /'
  fi
fi
for path in /usr/bin/pantheon-compositor /usr/bin/pantheon-rust-session \
            /usr/share/wayland-sessions/$session_name.desktop \
            /usr/lib/systemd/user/$compositor_template \
            /usr/lib/systemd/user/pantheon-wingpanel.service \
            /usr/lib/systemd/user/pantheon-dock.service; do
  if [[ -e $path ]]; then log "present: $path"; else log "absent:  $path"; fi
done
if unit_files=$(user_systemctl list-unit-files 2>/dev/null); then
  if grep -q '^pantheon-rust-compositor@' <<<"$unit_files"; then
    log "user manager: pantheon-rust units known"
  else
    log "user manager: pantheon-rust units not known yet (a daemon-reload after install fixes this)"
  fi
  service_state=$(user_systemctl is-active "$compositor_unit" 2>/dev/null || true)
  log "compositor service: ${service_state:-unknown}"
else
  log "user manager: desktop owner's bus unavailable; loaded service state unknown"
fi

# ---------------------------------------------------------------- helpers

install_deb() {
  local deb=$1 sha
  [[ -f $deb ]] || die "package not found: $deb"
  sha=$(sha256sum "$deb" | cut -d' ' -f1)
  log "installing $deb"
  log "  sha256 $sha"
  dpkg-deb --info "$deb" | sed -n '/^ Package:/p;/^ Version:/p;/^ Depends:/p' | sed 's/^/  /'
  # Never let an older build silently replace fixes already installed.
  local new_version have_version
  new_version=$(dpkg-deb -f "$deb" Version)
  have_version=$(dpkg-query -W -f='${Version}' pantheon-rust-compositor 2>/dev/null || true)
  if [[ -n $have_version ]] && dpkg --compare-versions "$new_version" lt "$have_version"; then
    die "refusing to downgrade pantheon-rust-compositor $have_version -> $new_version"
  fi
  as_root dpkg -i "$deb"
  reload_user_manager
  log "installed. The running session is unchanged; the Rust session is selectable at the next login."
}

write_autologin() {
  local value=$1 tmp
  # Keep the first backup: a second --select must not back up an already
  # modified file. Rewrite only the autologin-session key and keep the rest of
  # the drop-in (the [Seat:*] group header is required, or LightDM rejects the
  # whole file and falls back to the greeter/default session).
  if [[ -f $autologin_dropin && ! -f $autologin_dropin.pantheon-rust-backup ]]; then
    as_root cp -a "$autologin_dropin" "$autologin_dropin.pantheon-rust-backup"
    log "backup: $autologin_dropin.pantheon-rust-backup"
  fi
  tmp=$(mktemp)
  if [[ -f $autologin_dropin ]] && grep -q '^[[:space:]]*autologin-session=' "$autologin_dropin"; then
    sed "s|^\([[:space:]]*autologin-session=\).*|\1$value|" "$autologin_dropin" >"$tmp"
  elif [[ -f $autologin_dropin ]] && grep -q '^\[Seat:\*\]' "$autologin_dropin"; then
    sed "/^\[Seat:\*\]/a autologin-session=$value" "$autologin_dropin" >"$tmp"
  else
    { [[ -f $autologin_dropin ]] && cat "$autologin_dropin"; printf '[Seat:*]\nautologin-session=%s\n' "$value"; } >"$tmp"
  fi
  as_root install -m 0644 "$tmp" "$autologin_dropin"
  rm -f "$tmp"
  log "wrote autologin-session=$value to $autologin_dropin"
}

# ---------------------------------------------------------------- actions

case $action in
  dry-run)
    step "Plan (dry run; nothing was changed)"
    if [[ -n $deb_path ]]; then
      log "1. install $deb_path with dpkg -i"
    elif [[ $build == 1 ]]; then
      log "1. build the arm64 package with $component/build-deb.sh into a temporary directory"
      log "2. install the built package with dpkg -i"
    else
      log "1. install a package: pass --deb PATH, or --build to build one from this branch"
    fi
    log "3. systemctl --user daemon-reload (no unit is started or enabled)"
    log "4. verify the payload, the package and that Gala is still intact"
    log "Rollback at any time:"
    log "  sudo bash $0 --restore-gala --yes"
    log "  sudo bash $0 --uninstall --yes"
    ;;
  status)
    step "Result"
    if [[ -n $installed_version ]]; then
      log "pantheon-rust-compositor $installed_version is installed; autologin is ${autologin_session:-<unset>}."
    else
      log "pantheon-rust-compositor is not installed; autologin is ${autologin_session:-<unset>}."
    fi
    ;;
  verify)
    step "Verify"
    [[ -n $installed_version ]] || die "pantheon-rust-compositor is not installed"
    [[ -x /usr/bin/pantheon-compositor ]] || die "compositor binary missing"
    if ldd /usr/bin/pantheon-compositor | grep -q 'not found'; then
      ldd /usr/bin/pantheon-compositor | grep 'not found' | sed 's/^/  /'
      die "compositor binary has unresolved shared libraries"
    fi
    log "compositor binary resolves its shared libraries"
    [[ -f /usr/share/wayland-sessions/$session_name.desktop ]] || die "Rust session entry missing"
    log "Rust session entry present"
    [[ -x /usr/bin/gala ]] || die "Gala binary missing; rollback path broken"
    log "Gala rollback path intact"
    log "verify: installed package, payload, session entry and rollback are consistent"
    ;;
  install)
    need_yes
    step "Install"
    if [[ -n $deb_path ]]; then
      install_deb "$deb_path"
    elif [[ $build == 1 ]]; then
      outdir=$(mktemp -d)
      # shellcheck disable=SC2064
      trap "rm -rf '$outdir'" EXIT
      log "building the package from $repo (this takes a while)"
      OUTDIR="$outdir" bash "$component/build-deb.sh" >/dev/null
      built=$(ls -1 "$outdir"/pantheon-rust-compositor_*_arm64.deb | head -1)
      install_deb "$built"
    else
      die "pass --deb PATH or --build"
    fi
    step "Rollback"
    log "next login on Gala:  sudo bash $0 --restore-gala --yes"
    log "remove the package:  sudo bash $0 --uninstall --yes"
    log "Gala itself was never touched, so logging out and back in is enough if the Rust session misbehaves."
    ;;
  uninstall)
    need_yes
    step "Uninstall"
    if [[ -z $installed_version ]]; then
      log "pantheon-rust-compositor is not installed; nothing to remove"
      exit 0
    fi
    as_root dpkg -r pantheon-rust-compositor
    reload_user_manager
    log "removed $installed_version"
    if [[ $autologin_session == "$session_name" ]]; then
      warn "autologin still selects the removed Rust session; run --restore-gala --yes"
    fi
    ;;
  select)
    need_yes
    [[ -n $installed_version ]] || die "install the package first (--install --yes)"
    step "Select the Rust session for the next login"
    write_autologin "$session_name"
    log "The running session is untouched. The next login starts the Rust compositor."
    log "Rollback: sudo bash $0 --restore-gala --yes"
    ;;
  restore-gala)
    need_yes
    step "Restore the Gala session for the next login"
    if [[ -f $autologin_dropin.pantheon-rust-backup ]]; then
      as_root cp -a "$autologin_dropin.pantheon-rust-backup" "$autologin_dropin"
      log "restored $autologin_dropin from its backup"
    else
      write_autologin "$gala_session"
      log "(no backup was found)"
    fi
    log "The next login starts Gala again."
    ;;
esac
