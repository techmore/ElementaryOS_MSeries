#!/usr/bin/env bash
# Per-user follow-up for enhancements that need the real desktop user's HOME.
set -uo pipefail

PAYLOAD=${ELEMENTARY_MAC_PAYLOAD:-/usr/share/elementary-mac/mseries}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/elementary-mac-user-enhance
LOG=$STATE/last-run.log
ROOT_STATE=/var/lib/elementary-mac/enhance
mkdir -p "$STATE"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
done_already() { [[ -f $STATE/$1.done ]]; }
mark_done() { touch "$STATE/$1.done"; }

run_codexbar() {
  done_already codexbar && return 0
  [[ -f $ROOT_STATE/desktop-user-deps.done ]] || { log 'codexbar: waiting for system dependencies'; return 0; }
  log 'codexbar: installing ARM64 desktop and CLI for this user'
  if bash "$PAYLOAD/install-codexbar.sh" --skip-system-deps >>"$LOG" 2>&1; then
    mark_done codexbar
    log 'codexbar: installed'
  else
    log 'codexbar: failed; the user timer will retry'
  fi
}

run_netusage() {
  done_already netusage && return 0
  [[ -f /etc/polkit-1/rules.d/49-mseries-netusage.rules ]] || { log 'netusage: waiting for its system polkit rule'; return 0; }
  log 'netusage: installing and starting the user logger'
  if bash "$PAYLOAD/netspeed/netusage/install.sh" --user-only >>"$LOG" 2>&1; then
    mark_done netusage
    log 'netusage: installed'
  else
    log 'netusage: failed; the user timer will retry'
  fi
}

run_widevine() {
  done_already widevine && return 0
  local profile=${BRAVE_PROFILE_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/BraveSoftware/Brave-Browser}
  [[ -f $profile/Local\ State ]] || { log 'widevine: waiting for Brave to create a profile'; return 0; }
  pgrep -u "$(id -u)" -x brave >/dev/null && { log 'widevine: Brave is open; will retry after a later login'; return 0; }
  log 'widevine: installing DRM component for this Brave profile'
  if bash "$PAYLOAD/install-brave-widevine.sh" >>"$LOG" 2>&1; then
    mark_done widevine
    log 'widevine: installed'
  else
    log 'widevine: failed; the user timer will retry'
  fi
}

[[ -d $PAYLOAD ]] || { log "payload missing: $PAYLOAD"; exit 0; }
run_codexbar
run_netusage
run_widevine
if done_already codexbar && done_already netusage && done_already widevine; then
  # The timer is enabled globally, so a user cannot remove its enable symlink.
  # Stop it for this session; next login performs a cheap completion check.
  systemctl --user stop elementary-mac-user-enhance.timer >/dev/null 2>&1 || true
fi
