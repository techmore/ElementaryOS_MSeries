#!/bin/bash
# First-boot enhancements for an elementary OS (M-series) install: the ones that
# need network and a build, so they cannot be done while the root is built.
# Installed as /usr/sbin/elementary-mac-enhance and run once by
# elementary-mac-enhance.service.
#
#   elementary-mac-enhance --run                 do whatever is not done yet
#   elementary-mac-enhance --status              what is done / skipped / failed
#   elementary-mac-enhance --retry [MODULE]      forget a failure (or all) and run again
#   elementary-mac-enhance --run --with firefox  also install an optional module
#
# Modules, each independent and best-effort (a failure is logged and never stops
# the others or the boot):
#   brave       Brave browser from Brave's apt repository (key fingerprints pinned)
#   gestures    Touchegg touchpad gesture daemon, built from the upstream release
#   network     live download/upload speed and graph in the network indicator
#   quick       screen/keyboard brightness and the charge-limit switch in Quick Settings
#   sound       sound indicator icon initialisation fix
#   keyboard    keyboard indicator state fix
#   files       Files portal login-stall fix
#   osk         Gala on-screen-keyboard guard
#   firefox     (optional) Firefox from Mozilla's apt repository
#
# The patched components are built from pinned upstream commits and gated on the
# installed package version: on a different version the module is skipped with
# the reason in the log, never forced.
# shellcheck disable=SC1010  # "done" is a state name here, not the keyword
set -uo pipefail

STATE=${ELEMENTARY_MAC_STATE:-/var/lib/elementary-mac/enhance}
LOG=${ELEMENTARY_MAC_LOG:-/var/log/elementary-mac-enhance.log}
PAYLOAD=/usr/share/elementary-mac
MAX_ATTEMPTS=3
PATH=$PAYLOAD/shim:$PATH   # `sudo` as a no-op: the install scripts were written for a user account
export PATH DEBIAN_FRONTEND=noninteractive

DEFAULT=(brave gestures network quick sound keyboard files osk)
declare -A SCRIPT=(
  [brave]=install-brave.sh [gestures]=install-touchegg.sh
  [network]=install-network-throughput.sh [quick]=install-quick-settings-brightness.sh
  [sound]=install-sound-indicator-fix.sh [keyboard]=install-keyboard-indicator-fix.sh
  [files]=install-files-portal-fix.sh [osk]=install-gala-osk-fix.sh
  [firefox]=install-native-firefox.sh
)
# Build requirements per module (apt names). A module whose packages cannot be
# installed is skipped, not guessed at.
declare -A DEPS=(
  [brave]="curl gpg"
  [gestures]="cmake g++ git libinput-dev libudev-dev libpugixml-dev libcairo2-dev libgtk-3-dev libx11-dev libxtst-dev libxrandr-dev libxi-dev libsystemd-dev systemd-dev"
  [network]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnm-dev libnma-gtk4-dev libpolkit-gobject-1-dev"
  [quick]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnm-dev libpolkit-gobject-1-dev"
  [sound]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libpulse-dev libcanberra-dev libgee-0.8-dev"
  [keyboard]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libgnome-desktop-4-dev libibus-1.0-dev libgee-0.8-dev"
  [files]="git meson ninja-build valac pkg-config libgtk-3-dev libgranite-dev libhandy-1-dev libportal-dev libportal-gtk3-dev libpoppler-glib-dev libcanberra-dev libsqlite3-dev libgee-0.8-dev libgit2-glib-1.0-dev libcloudproviders-dev libnotify-dev libwingpanel-9-dev"
  [osk]="git meson ninja-build valac pkg-config python3 libmutter-18-dev libgala-dev libgranite-7-dev libgtk-4-dev libibus-1.0-dev libgee-0.8-dev"
  [firefox]="curl gpg"
)

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

state() { # state MODULE -> done | skipped | failed:N | pending
  local m=$1
  if [[ -f $STATE/$m.done ]]; then echo done
  elif [[ -f $STATE/$m.skipped ]]; then echo skipped
  elif [[ -f $STATE/$m.attempts ]]; then echo "failed:$(cat "$STATE/$m.attempts")"
  else echo pending; fi
}

have_network() { ip route 2>/dev/null | grep -q '^default '; }

wait_for_network() {
  local waited=0
  until have_network && curl -fsS -m 10 -o /dev/null https://deb.debian.org 2>/dev/null; do
    (( waited >= 300 )) && return 1
    sleep 10; (( waited += 10 ))
  done
}

run_module() {
  local m=$1 attempts out rc script
  script=$PAYLOAD/mseries/${SCRIPT[$m]}
  [[ -f $script ]] || { log "$m: payload missing ($script); skipped"; touch "$STATE/$m.skipped"; return; }
  attempts=$(cat "$STATE/$m.attempts" 2>/dev/null || echo 0)
  (( attempts >= MAX_ATTEMPTS )) && { log "$m: gave up after $attempts attempts (see $LOG; --retry $m)"; return; }

  log "$m: starting"
  if [[ -n ${DEPS[$m]} ]]; then
    # shellcheck disable=SC2086  # a word list on purpose
    if ! apt-get install -y --no-install-recommends ${DEPS[$m]} >>"$LOG" 2>&1; then
      apt-get update >>"$LOG" 2>&1
      # shellcheck disable=SC2086
      apt-get install -y --no-install-recommends ${DEPS[$m]} >>"$LOG" 2>&1 || {
        echo $((attempts + 1)) >"$STATE/$m.attempts"; log "$m: build requirements unavailable; will retry"; return; }
    fi
  fi

  out=$(mktemp)
  bash "$script" >"$out" 2>&1; rc=$?
  cat "$out" >>"$LOG"
  if (( rc == 0 )); then
    log "$m: done"; touch "$STATE/$m.done"; rm -f "$STATE/$m.attempts"
  elif grep -qE "targets .* (found|need)|This patch targets|Patch targets|Missing .*(tool|development files)" "$out"; then
    # Not applicable to this package version: a final answer, not a failure to retry.
    log "$m: not applicable here ($(grep -m1 -E 'targets' "$out" || echo see log)); skipped"
    touch "$STATE/$m.skipped"
  else
    echo $((attempts + 1)) >"$STATE/$m.attempts"
    log "$m: failed (exit $rc); attempt $((attempts + 1)) of $MAX_ATTEMPTS"
  fi
  unlink "$out"
}

status() {
  local m
  for m in "${DEFAULT[@]}" firefox; do printf '%-10s %s\n' "$m" "$(state "$m")"; done
  [[ -f $STATE/finished ]] && echo "all modules settled (service retired)"
  return 0
}

main() {
  local action=--run extra=() m target=""
  while (( $# )); do
    case $1 in
      --run | --status) action=$1 ;;
      --retry) action=--retry; [[ ${2:-} && ${2:0:2} != -- ]] && { target=$2; shift; } ;;
      --with) extra+=("${2:?--with needs a module}"); shift ;;
      -h | --help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; return 0 ;;
      *) echo "unknown argument: $1" >&2; return 2 ;;
    esac
    shift
  done

  mkdir -p "$STATE"
  case $action in
    --status) status; return ;;
    --retry)
      for m in "${DEFAULT[@]}" firefox; do
        [[ -z $target || $target == "$m" ]] && unlink "$STATE/$m.attempts" 2>/dev/null
      done
      rm -f "$STATE/finished"
      ;;
  esac
  [[ $EUID -eq 0 ]] || { echo "run as root" >&2; return 1; }
  grep -Faiq 'apple,' /proc/device-tree/compatible 2>/dev/null || { log "not an Apple device-tree machine; nothing to do"; touch "$STATE/finished"; return 0; }

  wait_for_network || { log "no network after 5 minutes; will try again next boot"; return 0; }
  apt-get update >>"$LOG" 2>&1 || true

  local todo=("${DEFAULT[@]}" "${extra[@]}")
  for m in "${todo[@]}"; do
    [[ -n ${SCRIPT[$m]:-} ]] || { log "unknown module $m"; continue; }
    case $(state "$m") in done | skipped) continue ;; esac
    run_module "$m"
  done

  # Retire the service once nothing is left to attempt.
  local pending=0
  for m in "${DEFAULT[@]}"; do
    case $(state "$m") in
      done | skipped) ;;
      failed:*) [[ $(state "$m") == failed:$MAX_ATTEMPTS ]] || pending=1 ;;
      *) pending=1 ;;
    esac
  done
  if (( ! pending )); then
    touch "$STATE/finished"
    systemctl disable elementary-mac-enhance.service >/dev/null 2>&1 || true
    log "all modules settled; first-boot enhancements finished"
  fi
  return 0
}

main "$@"
