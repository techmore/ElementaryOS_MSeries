#!/bin/bash
# One entry point for the M-series post-install customizations on an installed
# elementary OS system. Runs the existing installers in order; each is
# idempotent, and a failure is logged and never stops the rest.
#
#   bash mseries/post-install.sh --list                 stages and whether each is on by default
#   bash mseries/post-install.sh --dry-run              show what would run, change nothing
#   bash mseries/post-install.sh                        run the default stages
#   bash mseries/post-install.sh --only power,brave     run just these
#   bash mseries/post-install.sh --skip video           default stages minus these
#   bash mseries/post-install.sh --with signal,tether   default stages plus optional ones
#   bash mseries/post-install.sh --with apps           plus the preferred app set (APPS below)
#   bash mseries/post-install.sh --status               result of the last run
#
# Run as your normal desktop user, not root: the user-level stages configure
# your session and the system-level ones call sudo themselves (so run `sudo -v`
# first). Network is needed for the stages that download or build.
# Log in again afterwards so Gala and Wingpanel pick up the changes.
set -uo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
here=$repo/mseries
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/mseries-post-install
LOG=$STATE/last-run.log

# name|kind|default|script|what
STAGES=(
  "settings|user|on|apply-desktop-settings.py|Command-as-Ctrl, launcher, title buttons, screenshots, brightness keys"
  "brightness|user|on|install-brightness-bridge.sh|brightness bridge for Pantheon"
  "kbd-backlight|user|on|install-keyboard-backlight.sh|keyboard backlight helper"
  "screenshots|user|on|install-screenshot-shelf.sh|screenshot thumbnail shelf and Markup"
  "webrtc|user|on|install-webrtc.sh|phone remote desktop, view-only sharing and screen recording"
  "theme|user|on|install-theme-tweaks.sh|softer accents, larger corners, Ghostty palette"
  "docked-lid|user|on|install-docked-lid.sh|lock and blank panel instead of suspending when docked"
  "battery-eta|user|on|install-battery-eta.sh|time-to-full beside the battery icon"
  "power|system|on|install-power.sh|80% charge limit, battery CPU ceiling"
  "tuning|system|on|install-system-tuning.sh|system tuning from the 2026-10-12 audit"
  "audio|system|on|install-audio-stack.sh|speaker protection daemon"
  "brave|system|on|install-brave.sh|Brave from its apt repository"
  "widevine|user|on|install-brave-widevine.sh|Widevine DRM playback in Brave"
  "video|system|on|install-video-decode.sh|VA-API hardware video decode"
  "gestures|system|on|install-touchegg.sh|Touchegg touchpad gestures"
  "network|system|on|install-network-throughput.sh|network speed in the indicator"
  "netusage|user|on|netspeed/netusage/install.sh|Apps, Hosts and DNS network usage logging"
  "quick|system|on|install-quick-settings-brightness.sh|brightness and charge limit in Quick Settings"
  "sound|system|on|install-sound-indicator-fix.sh|sound indicator fix"
  "keyboard|system|on|install-keyboard-indicator-fix.sh|keyboard indicator fix"
  "files|system|on|install-files-portal-fix.sh|Files portal login-stall fix"
  "osk|system|on|install-gala-osk-fix.sh|Gala on-screen-keyboard guard"
  "firefox|system|off|install-native-firefox.sh|Firefox from Mozilla's apt repository (no snap)"
  "signal|user|off|install-signal.sh|Signal Desktop ARM64 beta"
  "tether|user|off|install-tether.sh|Tether iPhone pairing"
  "opencode|system|off|install-opencode-desktop.sh|OpenCode Desktop, built from source for arm64 (slow)"
  "codexbar|user|on|install-codexbar.sh|CodexBar ARM64 desktop and CLI"
  "codexbar-panel|system|on|install-codexbar-wingpanel.sh|CodexBar quota and usage indicator in Wingpanel"
  "corners|system|off|install-gala-screen-corners.sh|rounded screen corners (patched Gala)"
  "clockright|system|off|install-clockright-wingpanel.sh|right-side clock while the notch area is fixed"
  "drawers|system|off|install-gala-drawers.sh|hotkey drawers: pop an app up/down into a fixed screen zone"
)

# Preferred apps: `apps` expands to these in --with/--only. brave and codexbar
# are already on by default, so they are listed to make --only apps complete.
APPS=(brave firefox signal tether codexbar opencode)

field() { local IFS='|'; local -a f=($1); echo "${f[$2]}"; }
known() { local s; for s in "${STAGES[@]}"; do [[ $(field "$s" 0) == "$1" ]] && return 0; done; return 1; }

list_stages() {
  printf '%-14s %-7s %-4s %s\n' STAGE KIND DEF WHAT
  local s
  for s in "${STAGES[@]}"; do
    printf '%-14s %-7s %-4s %s\n' "$(field "$s" 0)" "$(field "$s" 1)" "$(field "$s" 2)" "$(field "$s" 4)"
  done
}

usage() { sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

only=() skip=() with=() dry=0
csv() { local IFS=,; read -ra "$1" <<<"$2"; }
while (( $# )); do
  case $1 in
    --list) list_stages; exit 0 ;;
    --status) cat "$STATE/summary" 2>/dev/null || echo "no previous run recorded"; exit 0 ;;
    --dry-run|-n) dry=1 ;;
    --only) csv only "${2:?--only needs a list}"; shift ;;
    --skip) csv skip "${2:?--skip needs a list}"; shift ;;
    --with) csv with "${2:?--with needs a list}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

expand_apps() { # name of array var
  local -n arr=$1; local out=() x
  for x in "${arr[@]}"; do if [[ $x == apps ]]; then out+=("${APPS[@]}"); else out+=("$x"); fi; done
  arr=("${out[@]}")
}
expand_apps only; expand_apps with; expand_apps skip

for n in "${only[@]}" "${skip[@]}" "${with[@]}"; do
  [[ -z $n ]] || known "$n" || { echo "unknown stage: $n (see --list)" >&2; exit 2; }
done
(( EUID == 0 )) && { echo "run as your desktop user, not root" >&2; exit 2; }

in_list() { local x=$1; shift; local i; for i in "$@"; do [[ $i == "$x" ]] && return 0; done; return 1; }

selected=()
for s in "${STAGES[@]}"; do
  n=$(field "$s" 0)
  if (( ${#only[@]} )); then
    in_list "$n" "${only[@]}" && selected+=("$s")
  elif in_list "$n" "${skip[@]}"; then
    continue
  elif [[ $(field "$s" 2) == on ]] || in_list "$n" "${with[@]}"; then
    selected+=("$s")
  fi
done

if (( dry )); then
  echo "dry run: nothing will be changed"
  for s in "${selected[@]}"; do
    script=$here/$(field "$s" 3)
    runner=bash
    [[ $script == *.py ]] && runner=python3
    printf '  [%s] %s %s\n' "$(field "$s" 0)" "$runner" "$script"
  done
  exit 0
fi

mkdir -p "$STATE"
: >"$LOG"
MSERIES_APT_BATCH_DIR=$(mktemp -d) || exit 1
export MSERIES_APT_BATCH_DIR
trap 'rm -rf -- "$MSERIES_APT_BATCH_DIR"' EXIT
ok=() failed=()
for s in "${selected[@]}"; do
  n=$(field "$s" 0)
  stage_started=$SECONDS
  echo "==> $n: $(field "$s" 4)"
  # pipefail makes the pipeline status the installer's own, not tee's
  script=$here/$(field "$s" 3)
  if [[ $script == *.py ]]; then
    if ( cd "$repo" && python3 "$script" ) 2>&1 | tee -a "$LOG"; then ok+=("$n"); else failed+=("$n"); fi
  elif ( cd "$repo" && bash "$script" ) 2>&1 | tee -a "$LOG"; then
    ok+=("$n")
  else
    failed+=("$n")
  fi
  echo "$n: elapsed $((SECONDS - stage_started))s" | tee -a "$LOG"
done

{
  echo "ran $(date '+%F %T')"
  echo "ok:     ${ok[*]:-none}"
  echo "failed: ${failed[*]:-none}"
} | tee "$STATE/summary"
echo "log: $LOG"
echo "Log out and back in to load Gala/Wingpanel changes."
(( ${#failed[@]} == 0 ))
