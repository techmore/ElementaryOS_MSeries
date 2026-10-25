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
#   elementary-mac-enhance --run --parallel[=N]  opt in: run independent modules at once (N jobs)
#   elementary-mac-enhance --timing              wall and CPU time of each module in the last run
#
# Modules, each independent and best-effort (a failure is logged and never stops
# the others or the boot):
#   brave       Brave browser from Brave's apt repository (key fingerprints pinned)
#   video       hardware video decode: builds the VA-API driver for the Apple Video Decoder from a
#               pinned commit (checksum-verified) and checks it with vainfo
#   gestures    Touchegg touchpad gesture daemon, built from the upstream release
#   network     live download/upload speed and graph in the network indicator
#   quick       screen/keyboard brightness and the charge-limit switch in Quick Settings
#   sound       sound indicator icon initialisation fix
#   keyboard    keyboard indicator state fix
#   files       Files portal login-stall fix
#   osk         Gala on-screen-keyboard guard
#   desktop-user-deps Qt runtime packages for the per-user CodexBar installer
#   netusage-policy   narrowly authorize the read-only DNS monitor
#   firefox     (optional) Firefox from Mozilla's apt repository
#
# The patched components are built from pinned upstream commits and gated on the
# installed package version: on a different version the module is skipped with
# the reason in the log, never forced.
#
# Build requirements for every pending module are installed in one apt-get call
# before the first module runs (#47); a module only installs its own when that
# combined step fails. A failure that would repeat (missing package, file or
# commit) is not retried on later boots; only network trouble is. `--retry`
# clears either kind.
#
# Timing (#47): every module that runs is timed (start, end, wall and CPU seconds,
# one JSON line each in $STATE/timing.jsonl); the run ends with a table sorted by
# wall time, a one-line summary and $STATE/timing-summary.json. A run that has
# nothing left to do leaves the previous timing in place.
#
# Parallel mode is opt-in and the default stays serial. Enable it with --parallel,
# or MSERIES_PARALLEL=1 (for the service: a drop-in with Environment=MSERIES_PARALLEL=1).
# MSERIES_JOBS=N sets the worker count (default: half the cores). Modules that hold
# the apt/dpkg lock never overlap one another, nor do the ones that replace
# Wingpanel plugins (the lock and dependency table, with the reason for each, is
# mseries/enhance-modules.json; the scheduler is mseries/modrun.py). MSERIES_SERIAL=1
# forces the serial path, and so does anything that makes parallel unsafe: no python3
# or scheduler files, one worker, or a failed combined requirements install (each module
# would then run its own apt-get).
# shellcheck disable=SC1010  # "done" is a state name here, not the keyword
set -uo pipefail

STATE=${ELEMENTARY_MAC_STATE:-/var/lib/elementary-mac/enhance}
LOG=${ELEMENTARY_MAC_LOG:-/var/log/elementary-mac-enhance.log}
PAYLOAD=${ELEMENTARY_MAC_PAYLOAD:-/usr/share/elementary-mac}
COMPATIBLE=${ELEMENTARY_MAC_COMPATIBLE:-/proc/device-tree/compatible}
MAX_ATTEMPTS=3
DEPS_READY=${ELEMENTARY_MAC_DEPS_READY:-0}   # 1 once the combined requirements install succeeded
SELF=$(readlink -f "$0")
MODRUN=${ELEMENTARY_MAC_MODRUN:-$PAYLOAD/mseries/modrun.py}
GRAPH=${ELEMENTARY_MAC_GRAPH:-$PAYLOAD/mseries/enhance-modules.json}
TIMING_LOG=$STATE/timing.jsonl
SUMMARY_JSON=$STATE/timing-summary.json
PARALLEL=${MSERIES_PARALLEL:-0}
# shellcheck source=mseries/lib-timing.sh
source "${ELEMENTARY_MAC_TIMING_LIB:-$PAYLOAD/mseries/lib-timing.sh}" 2>/dev/null ||
  { timing_begin() { :; }; timing_end() { :; }; timing_summary() { :; }; }
PATH=$PAYLOAD/shim:$PATH   # `sudo` as a no-op: the install scripts were written for a user account
export PATH DEBIAN_FRONTEND=noninteractive

DEFAULT=(brave video gestures network desktop-user-deps netusage-policy quick sound keyboard files osk battery-panel)
declare -A SCRIPT=(
  [brave]=install-brave.sh [video]=install-video-decode.sh [gestures]=install-touchegg.sh
  [network]=install-network-throughput.sh [quick]=install-quick-settings-brightness.sh
  [sound]=install-sound-indicator-fix.sh [keyboard]=install-keyboard-indicator-fix.sh
  [files]=install-files-portal-fix.sh [osk]=install-gala-osk-fix.sh
  [firefox]=install-native-firefox.sh
  [netusage-policy]=install-netusage-policy.sh
  [battery-panel]=install-battery-eta.sh
)
# Build requirements per module (apt names). A module whose packages cannot be
# installed is skipped, not guessed at.
declare -A DEPS=(
  [brave]="curl gpg bubblewrap xdg-dbus-proxy"
  [video]="meson ninja-build gcc pkg-config curl libva-dev libdrm-dev linux-libc-dev vainfo"
  [gestures]="cmake g++ git libinput-dev libudev-dev libpugixml-dev libcairo2-dev libgtk-3-dev libx11-dev libxtst-dev libxrandr-dev libxi-dev libsystemd-dev systemd-dev"
  [network]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnm-dev libnma-gtk4-dev libpolkit-gobject-1-dev"
  [quick]="libpackagekit-glib2-dev libaccountsservice-dev libportal-dev libwayland-dev git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libadwaita-1-dev libjson-glib-dev libnm-dev libpolkit-gobject-1-dev"
  [sound]="git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libpulse-dev libcanberra-dev libgee-0.8-dev"
  [keyboard]="libxml2-dev xkb-data git meson ninja-build valac gettext pkg-config libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libgnome-desktop-4-dev libibus-1.0-dev libgee-0.8-dev"
  [files]="git meson ninja-build valac pkg-config libgtk-3-dev libgranite-dev libhandy-1-dev libportal-dev libportal-gtk3-dev libpoppler-glib-dev libcanberra-dev libsqlite3-dev libgee-0.8-dev libgit2-glib-1.0-dev libcloudproviders-dev libnotify-dev libwingpanel-9-dev"
  [osk]="git meson ninja-build valac pkg-config python3 libmutter-18-dev libgala-dev libgranite-7-dev libgtk-4-dev libibus-1.0-dev libgee-0.8-dev"
  [battery-panel]="git meson ninja-build valac gettext pkg-config libgtop2-dev libudev-dev libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnotify-dev"
  [firefox]="curl gpg"
  [desktop-user-deps]="curl ca-certificates python3 unzip procps qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-layouts qml6-module-qtquick-templates qml6-module-qtquick-window qml6-module-qtqml-workerscript libqt6widgets6 libqt6svg6 qt6-wayland xdg-terminal-exec"
)

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }

state() { # state MODULE -> done | skipped | failed:N | pending
  local m=$1
  if [[ -f $STATE/$m.done ]]; then echo done
  elif [[ -f $STATE/$m.skipped ]]; then echo skipped
  elif [[ -f $STATE/$m.attempts ]]; then echo "failed:$(cat "$STATE/$m.attempts")"
  else echo pending; fi
}

# Output that means "try again later" rather than "this will fail the same way".
transient() { # transient OUTPUT-FILE
  grep -qiE 'could not resolve|temporary failure in name resolution|connection (timed out|reset|refused)|network is unreachable|failed to fetch|unable to connect|could not connect|curl: \((6|7|28|35|52|55|56)\)|tls handshake|timed out|rate limit|hash sum mismatch|HTTP/[0-9.]+ (429|502|503|504)' "$1"
}

# Record a failed step: another attempt next boot for network trouble, final
# otherwise (the reason is kept for --status). (#47)
fail_module() { # fail_module MODULE ATTEMPTS EXIT OUTPUT-FILE WHAT
  local m=$1 attempts=$2 rc=$3 out=$4 what=$5 reason
  if transient "$out"; then
    echo $((attempts + 1)) >"$STATE/$m.attempts"
    log "$m: $what failed (exit $rc), looks like a network problem; attempt $((attempts + 1)) of $MAX_ATTEMPTS"
    return
  fi
  reason=$(grep -m1 -iE 'unable to locate package|no such file|not found|fatal:|error' "$out" | head -c 160)
  echo "$MAX_ATTEMPTS" >"$STATE/$m.attempts"
  printf '%s\n' "${reason:-$what failed (exit $rc)}" >"$STATE/$m.reason"
  log "$m: $what failed (exit $rc) and would fail the same way again; not retried. Fix it, then: elementary-mac-enhance --retry $m (${reason:-see $LOG})"
}

# One apt-get for the requirements of every module that is still going to run,
# so the same packages are not resolved and fetched up to twelve times (#47).
# When it fails (one unavailable package fails the whole transaction) each
# module falls back to installing its own, so one bad package blocks only its module.
install_requirements_once() { # install_requirements_once MODULE...
  local m p pkgs=() seen=" "
  for m in "$@"; do
    case $(state "$m") in done | skipped | "failed:$MAX_ATTEMPTS") continue ;; esac
    [[ -z ${SCRIPT[$m]:-} || -f $PAYLOAD/mseries/${SCRIPT[$m]} ]] || continue   # skipped as missing payload
    for p in ${DEPS[$m]:-}; do
      [[ $seen == *" $p "* ]] || { pkgs+=("$p"); seen+="$p "; }
    done
  done
  (( ${#pkgs[@]} )) || return 0
  log "installing the build requirements of all pending modules in one step (${#pkgs[@]} packages)"
  if apt-get install -y --no-install-recommends "${pkgs[@]}" >>"$LOG" 2>&1; then
    DEPS_READY=1
  else
    log "combined install failed; each module installs its own requirements"
  fi
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
  script=${SCRIPT[$m]:-}
  if [[ -n $script ]]; then
    script=$PAYLOAD/mseries/$script
    [[ -f $script ]] || { log "$m: payload missing ($script); skipped"; touch "$STATE/$m.skipped"; return; }
  fi
  attempts=$(cat "$STATE/$m.attempts" 2>/dev/null || echo 0)
  (( attempts >= MAX_ATTEMPTS )) && { log "$m: gave up after $attempts attempts (see $LOG; --retry $m)"; return; }

  log "$m: starting"
  out=$(mktemp)
  if [[ -n ${DEPS[$m]:-} ]] && (( ! DEPS_READY )); then
    # shellcheck disable=SC2086  # a word list on purpose
    if ! apt-get install -y --no-install-recommends ${DEPS[$m]} >"$out" 2>&1; then
      apt-get update >>"$out" 2>&1
      # shellcheck disable=SC2086
      apt-get install -y --no-install-recommends ${DEPS[$m]} >>"$out" 2>&1; rc=$?
      cat "$out" >>"$LOG"
      if (( rc != 0 )); then
        fail_module "$m" "$attempts" "$rc" "$out" "installing build requirements"
        unlink "$out"
        return
      fi
    else
      cat "$out" >>"$LOG"
    fi
  fi

  if [[ -z $script ]]; then
    log "$m: dependencies installed"
    touch "$STATE/$m.done"
    rm -f "$STATE/$m.attempts" "$STATE/$m.reason"
    unlink "$out"
    return
  fi

  bash "$script" >"$out" 2>&1; rc=$?
  cat "$out" >>"$LOG"
  if (( rc == 0 )); then
    log "$m: done"; touch "$STATE/$m.done"; rm -f "$STATE/$m.attempts" "$STATE/$m.reason"
  elif grep -qE "targets .* (found|need)|This patch targets|Patch targets|not applicable here|Not an Apple" "$out"; then
    # Not applicable to this package version: a final answer, not a failure to retry.
    log "$m: not applicable here ($(grep -m1 -E 'targets' "$out" || echo see log)); skipped"
    touch "$STATE/$m.skipped"
  else
    fail_module "$m" "$attempts" "$rc" "$out" "install"
  fi
  unlink "$out"
}

# -- timing (#47) ----------------------------------------------------------------
# run_module with start, end, wall and CPU time written to the timing log
# (the helpers are mseries/lib-timing.sh; without them nothing is timed).
time_module() { # time_module MODULE
  local m=$1 status st
  timing_begin
  run_module "$m"
  case $(state "$m") in done) status=ok st=0 ;; skipped) status=not-applicable st=77 ;; *) status=failed st=1 ;; esac
  timing_end "$TIMING_LOG" "$m" "$status" "$st"
}

# Table sorted by wall time and a one-line summary into the log; with a mode, also the JSON file.
print_timing() { # print_timing [MODE]
  timing_summary "$TIMING_LOG" "${1:-}" "${1:+$SUMMARY_JSON}" | tee -a "$LOG"
}

# -- parallel mode (opt-in) -------------------------------------------------------
# Why parallel cannot be used now, or nothing when it can.
parallel_blocker() { # parallel_blocker JOBS MODULE...
  local jobs=$1 m; shift
  [[ ${MSERIES_SERIAL:-} == 1 ]] && { echo "MSERIES_SERIAL=1"; return; }
  command -v python3 >/dev/null 2>&1 || { echo "python3 is not installed"; return; }
  [[ -f $MODRUN && -f $GRAPH ]] || { echo "scheduler files missing from the payload"; return; }
  (( jobs > 1 )) || { echo "only one worker"; return; }
  (( DEPS_READY )) || { echo "the combined requirements install did not complete, so modules would each run apt-get"; return; }
  python3 "$MODRUN" check --graph "$GRAPH" --only "$(IFS=,; echo "$*")" >/dev/null 2>&1 ||
    echo "a module is missing from $GRAPH"
}

# Run the modules through the scheduler, each in its own process with its own log,
# then append the logs in module order so the combined log reads the same every time.
run_parallel() { # run_parallel JOBS MODULE...
  local jobs=$1 m cmd; shift
  local logs=$STATE/logs
  rm -rf "$logs"; mkdir -p "$logs"
  printf -v cmd '%q ' env "ELEMENTARY_MAC_LOG=$logs/{name}.log" "ELEMENTARY_MAC_DEPS_READY=$DEPS_READY" bash "$SELF" --one '{name}'
  log "running $# modules with up to $jobs at a time (apt holders and Wingpanel plugins stay one at a time)"
  python3 "$MODRUN" run --graph "$GRAPH" --only "$(IFS=,; echo "$*")" --jobs "$jobs" --cmd "$cmd" \
    --timing-log "$TIMING_LOG" --summary-json "$SUMMARY_JSON" --no-replay | tee -a "$LOG"
  for m in "$@"; do
    [[ -f $logs/$m.log ]] && cat "$logs/$m.log" >>"$LOG"
  done
  rm -rf "$logs"
}

status() {
  local m s
  for m in "${DEFAULT[@]}" firefox; do
    s=$(state "$m")
    [[ -f $STATE/$m.reason ]] && s="$s (not retried: $(cat "$STATE/$m.reason"); fix, then --retry $m)"
    printf '%-10s %s\n' "$m" "$s"
  done
  [[ -f $STATE/finished ]] && echo "all modules settled (service retired)"
  return 0
}

main() {
  local action=--run extra=() m target=""
  while (( $# )); do
    case $1 in
      --run | --status | --timing) action=$1 ;;
      --one) action=--one; target=${2:?--one needs a module}; shift ;;
      --parallel) PARALLEL=1 ;;
      --parallel=*) PARALLEL=1; MSERIES_JOBS=${1#--parallel=} ;;
      --retry) action=--retry; [[ ${2:-} && ${2:0:2} != -- ]] && { target=$2; shift; } ;;
      --with) extra+=("${2:?--with needs a module}"); shift ;;
      -h | --help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; return 0 ;;
      *) echo "unknown argument: $1" >&2; return 2 ;;
    esac
    shift
  done

  mkdir -p "$STATE"
  case $action in
    --status) status; return ;;
    --timing)
      [[ -s $TIMING_LOG ]] || { echo "no timing recorded yet"; return 0; }
      timing_summary "$TIMING_LOG"; return ;;
    --one)   # internal: one module for the parallel scheduler; the parent did the checks
      [[ -n ${SCRIPT[$target]:-} || -n ${DEPS[$target]:-} ]] || { log "unknown module $target"; return 1; }
      run_module "$target"
      case $(state "$target") in done) return 0 ;; skipped) return 77 ;; *) return 1 ;; esac ;;
    --retry)
      for m in "${DEFAULT[@]}" firefox; do
        [[ -z $target || $target == "$m" ]] && rm -f "$STATE/$m.attempts" "$STATE/$m.reason"
      done
      rm -f "$STATE/finished"
      ;;
  esac
  # ELEMENTARY_MAC_FAKE_ROOT=1 is for the test suite, which puts a fake apt-get on PATH.
  [[ $EUID -eq 0 || ${ELEMENTARY_MAC_FAKE_ROOT:-} == 1 ]] || { echo "run as root" >&2; return 1; }
  grep -Faiq 'apple,' "$COMPATIBLE" 2>/dev/null || { log "not an Apple device-tree machine; nothing to do"; touch "$STATE/finished"; return 0; }

  wait_for_network || { log "no network after 5 minutes; will try again next boot"; return 0; }
  apt-get update >>"$LOG" 2>&1 || true

  local todo=("${DEFAULT[@]}" "${extra[@]}") runnable=() jobs reason
  install_requirements_once "${todo[@]}"
  for m in "${todo[@]}"; do
    [[ -n ${SCRIPT[$m]:-} || -n ${DEPS[$m]:-} ]] || { log "unknown module $m"; continue; }
    case $(state "$m") in done | skipped) continue ;; esac
    runnable+=("$m")
  done
  (( ${#runnable[@]} )) && : >"$TIMING_LOG"   # a run with nothing to do keeps the last real timing
  jobs=${MSERIES_JOBS:-$(( $(nproc 2>/dev/null || echo 2) / 2 ))}
  [[ $jobs =~ ^[0-9]+$ ]] || jobs=1
  if [[ $PARALLEL == 1 ]] && (( ${#runnable[@]} )); then
    reason=$(parallel_blocker "$jobs" "${runnable[@]}")
    if [[ -z $reason ]]; then
      run_parallel "$jobs" "${runnable[@]}"
      runnable=()
    else
      log "parallel mode requested but not used: $reason; running one at a time"
    fi
  fi
  for m in "${runnable[@]}"; do
    time_module "$m"
  done
  (( ${#runnable[@]} )) && print_timing serial

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
