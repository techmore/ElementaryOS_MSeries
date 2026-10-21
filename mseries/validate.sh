#!/usr/bin/env bash
# Run the M-series wiring checks locally: the same syntax, lint and unit checks
# that the `validate` job of .github/workflows/validate-mseries.yml runs, plus
# the style checks for the plugin packaging (mseries-debs.yml). No image is
# built and nothing is downloaded, so a full run takes a minute or two.
#
#   bash mseries/validate.sh                  run every check, summary at the end
#   bash mseries/validate.sh --list           print the groups and check names
#   bash mseries/validate.sh --only codexbar  run the checks whose group or name
#                                             contains the text (repeatable)
#   bash mseries/validate.sh --skip dictation leave out matching checks (repeatable)
#   bash mseries/validate.sh --fail-fast      stop at the first failure
#   bash mseries/validate.sh --verbose        stream each check's output
#   just check [ARGS...]                      the same, from the repository root
#
# Exit status: 0 when every selected check passed, 1 when one or more failed,
# 2 for a usage error or when nothing matched. A failed check prints the tail
# of its log; every log stays in $TMPDIR/mseries-validate.<pid>/ when anything
# failed and is removed after a clean run.
#
# Needs: bash, python3, shellcheck, node (sudo apt install shellcheck nodejs).
# A missing tool fails the checks that use it and says what to install.
#
# Adding a check: add one `check GROUP "NAME" 'COMMAND'` line below (the
# command runs from the repository root with `bash -o pipefail -c`). CI calls
# this script, so a check added here runs on every pull request too.
set -uo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root" || exit 2

mode=run
fail_fast=0
verbose=0
only=()
skip=()
while (( $# )); do
  case $1 in
    --list) mode=list ;;
    --only) [[ ${2:-} ]] || { echo "--only needs a pattern" >&2; exit 2; }; only+=("$2"); shift ;;
    --skip) [[ ${2:-} ]] || { echo "--skip needs a pattern" >&2; exit 2; }; skip+=("$2"); shift ;;
    --fail-fast) fail_fast=1 ;;
    --verbose | -v) verbose=1 ;;
    -h | --help) sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
  shift
done

log_dir=$(mktemp -d "${TMPDIR:-/tmp}/mseries-validate.XXXXXX") || exit 2
passed=0
failed=0
selected=0
failed_names=()
missing_tools=()
if [[ -t 1 ]]; then
  c_ok=$'\e[32m' c_fail=$'\e[31m' c_dim=$'\e[2m' c_off=$'\e[0m'
else
  c_ok='' c_fail='' c_dim='' c_off=''
fi

# tool NAME [APT-PACKAGE]: record a missing tool once; return 1 when absent.
tool() {
  command -v "$1" >/dev/null 2>&1 && return 0
  local hint="sudo apt install ${2:-$1}"
  [[ " ${missing_tools[*]:-} " == *" $1 "* ]] || missing_tools+=("$1")
  echo "$1 is not installed ($hint)"
  return 1
}

matches() { # matches GROUP NAME -> selected by --only/--skip?
  local key="$1 $2" p
  if (( ${#only[@]} )); then
    local hit=0
    for p in "${only[@]}"; do [[ $key == *"$p"* ]] && hit=1; done
    (( hit )) || return 1
  fi
  for p in "${skip[@]}"; do [[ $key == *"$p"* ]] && return 1; done
  return 0
}

# check GROUP NAME COMMAND
check() {
  local group=$1 name=$2 cmd=$3
  matches "$group" "$name" || return 0
  (( selected++ ))
  if [[ $mode == list ]]; then
    printf '%-12s %s\n' "$group" "$name"
    return 0
  fi
  local log="$log_dir/$selected.log" start rc elapsed
  { echo "# $group: $name"; echo "# $cmd"; } >"$log"
  start=$SECONDS
  # Name a missing interpreter or linter instead of a bare "command not found".
  local first=${cmd%% *}
  first=${first%%[!A-Za-z0-9_.-]*}   # drop a trailing ';' or redirection
  if [[ $first == node ]]; then tool node nodejs; else tool "$first"; fi >>"$log" 2>&1 || true
  if (( verbose )); then
    printf '%s--- %s: %s%s\n' "$c_dim" "$group" "$name" "$c_off"
    bash -o pipefail -c "$cmd" 2>&1 | tee -a "$log"
    rc=${PIPESTATUS[0]}
  else
    bash -o pipefail -c "$cmd" >>"$log" 2>&1
    rc=$?
  fi
  elapsed=$(( SECONDS - start ))
  if (( rc == 0 )); then
    (( passed++ ))
    printf '%sok%s    %-12s %s %s(%ss)%s\n' "$c_ok" "$c_off" "$group" "$name" "$c_dim" "$elapsed" "$c_off"
  else
    (( failed++ ))
    failed_names+=("$group: $name")
    printf '%sFAIL%s  %-12s %s (exit %s, %ss)\n' "$c_fail" "$c_off" "$group" "$name" "$rc" "$elapsed"
    if (( ! verbose )); then
      sed -n '3,$p' "$log" | tail -n 25 | sed 's/^/      /'
      printf '      %slog: %s%s\n' "$c_dim" "$log" "$c_off"
    fi
    if (( fail_fast )); then
      finish
    fi
  fi
}

finish() {
  if [[ $mode == list ]]; then
    echo "$selected checks"
    exit 0
  fi
  echo
  if (( selected == 0 )); then
    echo "no checks matched (see --list)" >&2
    rmdir "$log_dir" 2>/dev/null
    exit 2
  fi
  if (( failed )); then
    echo "${c_fail}$failed of $selected checks failed${c_off}, $passed passed:"
    printf '  - %s\n' "${failed_names[@]}"
    if (( ${#missing_tools[@]} )); then
      echo "missing tools: ${missing_tools[*]} (sudo apt install ${missing_tools[*]/node/nodejs})"
    fi
    echo "logs: $log_dir"
    exit 1
  fi
  echo "${c_ok}all $selected checks passed${c_off}"
  rm -rf "$log_dir"
  exit 0
}

# ---------------------------------------------------------------------------
# The checks. Keep the commands identical to what a developer would type; CI
# runs this same file (validate-mseries.yml), so there is one list to maintain.
default_checks() {

# -- syntax: every shell script and Python file the image or installer runs --
check syntax 'mkosi apple-silicon hooks' \
  'bash -n mkosi.images/apple-silicon/mkosi.postinst.chroot mkosi.images/apple-silicon/mkosi.finalize mkosi.images/apple-silicon/build-network-indicator mkosi.images/apple-silicon/build-local-ai'
check syntax 'mkosi apple-silicon extra sbin' \
  'bash -n mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-firmware'
check syntax 'mseries-brightness (py_compile)' \
  'python3 -m py_compile mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness'
check syntax 'assemble-iso.sh, local-build-worker.sh' \
  'bash -n assemble-iso.sh mseries/local-build-worker.sh'
check syntax 'transform/elementary-grow.sh, bin/elementary-mac-setup' \
  'bash -n transform/elementary-grow.sh bin/elementary-mac-setup'
check syntax 'install-*.sh, lib-backup.sh, mkinitcpio-snippet, disable-notch' \
  'for f in mseries/install-*.sh mseries/lib-backup.sh mseries/boot/mkinitcpio-snippet mseries/disable-notch-for-pantheon.sh; do bash -n "$f" || exit 1; done'
check syntax 'local-ai/*.sh and *.py' \
  'for f in mseries/local-ai/*.sh; do bash -n "$f" || exit 1; done; python3 -m py_compile mseries/local-ai/*.py'
check syntax 'share-cost/*.sh and *.py' \
  'for f in mseries/share-cost/*.sh; do bash -n "$f" || exit 1; done; python3 -m py_compile mseries/share-cost/summarize-share-cost.py mseries/share-cost/compare-share-cost.py'
check syntax 'pantheon-rust-compositor/*.sh and summarize-metrics.py' \
  'for f in mseries/pantheon-rust-compositor/*.sh; do bash -n "$f" || exit 1; done; python3 -m py_compile mseries/pantheon-rust-compositor/summarize-metrics.py'
check syntax 'fairydust/debian scripts' \
  'bash -n mseries/fairydust/debian/build.sh mseries/fairydust/debian/fetch-asahi-boot-packages.sh; python3 -m py_compile mseries/fairydust/debian/assemble-m1n1-bootbin.py mseries/fairydust/debian/verify-m1n1-esp.py mseries/fairydust/debian/monitor.py mseries/check-kernel-config.py'
check syntax 'fairydust/usb4 scripts' \
  'bash -n mseries/fairydust/usb4/test-dp-tunnel.sh; python3 -m py_compile mseries/fairydust/usb4/*.py mseries/fairydust/usb4/tools/*.py'
check syntax 'aurora-sep installers' \
  'bash -n mseries/aurora-sep/install-aurora-sep.sh mseries/aurora-sep/install-touchid-gui.sh'
check syntax 'iso-label.sh, vms/mseries-vm' \
  'bash -n mseries/iso-label.sh mseries/test-iso-label.sh mseries/vms/mseries-vm'
check syntax 'codexbar scripts' \
  'bash -n mseries/install-signal.sh mseries/install-codexbar.sh mseries/deploy-codexbar.sh mseries/lib-codexbar.sh mseries/install-codexbar-wingpanel.sh mseries/check-codexbar-port.sh'
check syntax 'modrun.py, installer-speed.py, post-install.sh' \
  'python3 -m py_compile mseries/modrun.py mseries/benchmarks/installer-speed.py; bash -n mseries/post-install.sh'
check syntax 'display-space/*.py, test-notch-layout.sh, apply-desktop-settings.py' \
  'python3 -m py_compile mseries/display-space/*.py mseries/apply-desktop-settings.py; bash -n mseries/display-space/test-notch-layout.sh'
check syntax 'power scripts' \
  'bash -n mseries/power/mseries-power mseries/power/vrr-check.sh mseries/power/macos-baseline/make_test_videos.sh; python3 -m py_compile mseries/power/macos-baseline/*.py'

# -- shellcheck: the scripts that run as root on a user's Mac -----------------
check shellcheck 'installer, enhancements, boot and VM scripts' \
  'shellcheck -S warning bin/elementary-mac-setup transform/elementary-grow.sh mseries/install-unlock-screen.sh mseries/install-pantheon-rust-compositor.sh mseries/install-boot-isolation.sh mseries/lib-backup.sh mseries/boot/mkinitcpio-snippet mseries/enhance.sh mseries/enhance-firstboot.sh mseries/install-brave.sh mseries/install-video-decode.sh mseries/test-installer-flow.sh mseries/vms/mseries-vm mseries/vms/test-mseries-vm.sh mseries/install-machine-lab.sh mseries/machine-lab/build-deb.sh mseries/machine-lab/launcher/run-vm.sh mseries/install-quieter-sound-theme.sh mseries/test-quieter-sound-theme.sh mseries/aurora-sep/install-aurora-sep.sh mseries/aurora-sep/install-touchid-gui.sh mseries/lib-build.sh mseries/lib-timing.sh mseries/test-enhance-firstboot.sh mseries/test-build-ccache.sh mseries/test-post-install-timing.sh'
check shellcheck 'video-decode, widevine' \
  'shellcheck -S warning mseries/video-decode/brave-youtube mseries/install-brave-widevine.sh'
check shellcheck 'calendar, homeboard' \
  'shellcheck -S warning mseries/calendar/ci-test-agenda.sh mseries/install-homeboard-sync.sh'
check shellcheck 'codexbar' \
  'shellcheck -S warning mseries/lib-codexbar.sh mseries/deploy-codexbar.sh mseries/install-codexbar.sh mseries/install-codexbar-wingpanel.sh mseries/check-codexbar-port.sh mseries/codexbar-wingpanel/probe/ci-build-deps.sh mseries/codexbar-wingpanel/probe/run-grok-probe.sh'

# -- installer: the one-command install, first boot and the VM tool ----------
check installer 'test-elementary-mac-setup.sh' 'bash mseries/test-elementary-mac-setup.sh'
check installer 'test-installer-flow.sh' 'bash mseries/test-installer-flow.sh'
check installer 'test-iso-label.sh' 'bash mseries/test-iso-label.sh'
check installer 'test-enhance-firstboot.sh' 'bash mseries/test-enhance-firstboot.sh'
check installer 'test-post-install-timing.sh' 'bash mseries/test-post-install-timing.sh'
check installer 'test-build-ccache.sh' 'bash mseries/test-build-ccache.sh'
check installer 'test-modrun.py' 'python3 mseries/test-modrun.py'
check installer 'test-greeter-obex-fix.sh' 'bash mseries/test-greeter-obex-fix.sh'
check installer 'test-quieter-sound-theme.sh' 'bash mseries/test-quieter-sound-theme.sh'
check installer 'vms/test-mseries-vm.sh' 'bash mseries/vms/test-mseries-vm.sh'
check installer 'test-local-build-preflight.py' 'python3 mseries/test-local-build-preflight.py'
check installer 'test-image-wiring.py' 'python3 mseries/test-image-wiring.py'
check installer 'test-wifi-resume.py' 'python3 mseries/test-wifi-resume.py'
check installer 'test-signal-accent.py' 'python3 mseries/test-signal-accent.py'

# -- kernel: boot assets, kernel config, Fairydust/USB4 tooling --------------
check kernel 'fairydust/debian/test-assemble-m1n1-bootbin.py' 'python3 mseries/fairydust/debian/test-assemble-m1n1-bootbin.py'
check kernel 'fairydust/debian/test-verify-m1n1-esp.py' 'python3 mseries/fairydust/debian/test-verify-m1n1-esp.py'
check kernel 'fairydust/usb4/test-*.py' 'for f in mseries/fairydust/usb4/test-*.py; do python3 "$f" || exit 1; done'
check kernel 'fairydust/usb4/tools/test-staging-tools.py' 'python3 mseries/fairydust/usb4/tools/test-staging-tools.py'
check kernel 'boot/test-prepare-uki-kernels.py' 'python3 mseries/boot/test-prepare-uki-kernels.py'
check kernel 'test-kernel-config.py' 'python3 mseries/test-kernel-config.py'
check kernel 'aurora unit tests' "python3 -m unittest discover -s mseries/aurora -p 'test_*.py'"
check kernel 'aurora-sep/test_touchid_core.py' 'python3 mseries/aurora-sep/test_touchid_core.py'

# -- power ---------------------------------------------------------------------
check power 'test-power-cap.py' 'python3 mseries/test-power-cap.py'
check power 'test-power-install.py' 'python3 mseries/test-power-install.py'
check power 'macos-baseline unit tests' "python3 -m unittest discover -s mseries/power/macos-baseline -p 'test_*.py'"
check power 'share-cost tests' 'python3 mseries/share-cost/test-summarize-share-cost.py && python3 mseries/share-cost/test-compare-share-cost.py'

# -- desktop: panel layout, brightness, audio, video, compositor metrics -----
check desktop 'display-space unit tests' "python3 -m unittest discover -s mseries/display-space -p 'test_*.py'"
check desktop 'brightness unit tests' "python3 -m unittest discover -s mseries/brightness -p 'test_*.py'"
check desktop 'keyboard-backlight unit tests' "python3 -m unittest discover -s mseries/keyboard-backlight -p 'test_*.py'"
check desktop 'audio unit tests' "python3 -m unittest discover -s mseries/audio -p 'test_*.py'"
check desktop 'airplay unit tests' "python3 -m unittest discover -s mseries/airplay -p 'test_*.py'"
check desktop 'video-decode/test-brave-factory.py' 'python3 mseries/video-decode/test-brave-factory.py'
check desktop 'video-decode/test-youtube-launch.py' 'python3 mseries/video-decode/test-youtube-launch.py'
check desktop 'pantheon-rust-compositor metrics' \
  'python3 mseries/pantheon-rust-compositor/test-summarize-metrics.py && python3 mseries/pantheon-rust-compositor/summarize-metrics.py mseries/pantheon-rust-compositor/metrics/*.csv > /dev/null'

# -- codexbar: the CodexBar port's cache, sessions, accounts and wrappers ----
check codexbar 'test-codexbar-deploy.py' 'python3 mseries/test-codexbar-deploy.py'
check codexbar 'test-codexbar-cache.py' 'python3 mseries/test-codexbar-cache.py'
check codexbar 'test-codexbar-sessions.py' 'python3 mseries/test-codexbar-sessions.py'
check codexbar 'test-codexbar-performance.py' 'python3 mseries/test-codexbar-performance.py'
check codexbar 'test-codexbar-accounts.py' 'python3 mseries/test-codexbar-accounts.py'
check codexbar 'test-codexbar-claude.py' 'python3 mseries/test-codexbar-claude.py'
check codexbar 'test-codexbar-claude-history.py' 'python3 mseries/test-codexbar-claude-history.py'
check codexbar 'test-codexbar-claude-handoff.py' 'python3 mseries/test-codexbar-claude-handoff.py'
check codexbar 'test-codexbar-wrapper.py' 'python3 mseries/test-codexbar-wrapper.py'
check codexbar 'test-codexbar-opencode-local.py' 'python3 mseries/test-codexbar-opencode-local.py'
check codexbar 'test-codexbar-opencode-login.py' 'python3 mseries/test-codexbar-opencode-login.py'

# -- local-ai and dictation ----------------------------------------------------
check local-ai 'local-ai/test_people_watch.py' 'python3 mseries/local-ai/test_people_watch.py'
check local-ai 'local-ai unit tests' "python3 -m unittest discover -s mseries/local-ai -p 'test_*.py'"
check dictation 'dictation unit tests' "python3 -m unittest discover -s mseries/dictation -p 'test_*.py'"

# -- docs: the build-status pages under docs/ ---------------------------------
check docs 'test-build-status.mjs' 'node mseries/test-build-status.mjs'
check docs 'test-local-build-status.mjs' 'node mseries/test-local-build-status.mjs'

# -- debs: style checks for the plugin packaging (mseries-debs.yml) ----------
check debs 'packaging scripts (bash -n, shellcheck)' \
  'bash -n mseries/debs/build.sh mseries/debs/test-divert.sh mseries/quick-settings/prepare-source.sh mseries/calendar/test-agenda.sh && shellcheck -S warning mseries/debs/build.sh mseries/debs/test-divert.sh mseries/quick-settings/prepare-source.sh mseries/calendar/test-agenda.sh'
check debs 'calendar data bundled in the patch' 'python3 mseries/calendar/check-bundled-data.py'
check debs 'panel-factory-pins.json parses' 'python3 -c "import json,sys; json.load(open(\"mseries/panel-factory-pins.json\"))"'

# -- self: this script ---------------------------------------------------------
check self 'validate.sh (shellcheck, test-validate.sh)' \
  'shellcheck -S warning mseries/validate.sh mseries/test-validate.sh && bash mseries/test-validate.sh'
}

# MSERIES_VALIDATE_CHECKS=file replaces the built-in list (test-validate.sh uses it).
if [[ -n ${MSERIES_VALIDATE_CHECKS:-} ]]; then
  # shellcheck disable=SC1090  # a test fixture, chosen at run time
  source "$MSERIES_VALIDATE_CHECKS"
else
  default_checks
fi
finish
