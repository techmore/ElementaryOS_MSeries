#!/usr/bin/env bash
# Apply the repository fixes that need root on the running M1 Pro, in one safe pass.
#
#   bash mseries/apply-pending.sh --dry-run        # print every command, change nothing
#   bash mseries/apply-pending.sh                   # apply all steps (asks for your password once)
#   bash mseries/apply-pending.sh --only wifi,power # just some steps
#   bash mseries/apply-pending.sh --list            # list the steps
#
# Run it as your normal user, not with sudo: each privileged command uses sudo itself.
# Steps (all idempotent; a replaced file is first copied to <file>.pre-mseries if no backup exists yet):
#   wifi      install the fixed mseries-wifi-resume-fix, load brcmfmac if it is missing, clear the failed unit
#   power     drop the old multi-user.target link, reinstall mseries-power (WantedBy=graphical.target)
#   polkit    install the DNS-logger rule so the ten-minute password prompt stops
#   greeter   install the obexd stop-timeout drop-in for the LightDM greeter
#   wattmeter (optional, --only wattmeter) build the patched Power indicator with a live watts label and install it
# It never touches the bootloader, kernel, initramfs or the audio stack (AGENTS.md).
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ALL=(wifi power polkit greeter)
OPTIONAL=(wattmeter)   # only with --only: builds and replaces a panel module, restarts Wingpanel
dry=0 only=() failures=()

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) dry=1 ;;
    --only) shift; IFS=, read -r -a only <<<"${1:-}" ;;
    --list) printf '%s\n' "${ALL[@]}"; printf '%s (optional, use --only)\n' "${OPTIONAL[@]}"; exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
[[ $EUID -ne 0 ]] || { echo "Run this as your normal user, not root; it calls sudo where needed." >&2; exit 2; }
for step in "${only[@]}"; do
  [[ " ${ALL[*]} ${OPTIONAL[*]} " == *" $step "* ]] || { echo "Unknown step: $step (see --list)" >&2; exit 2; }
done
[[ ${#only[@]} -gt 0 ]] || only=("${ALL[@]}")

run() {  # run COMMAND...: print it, run it unless --dry-run
  printf '  $ %s\n' "$*"
  [[ $dry -eq 1 ]] || "$@"
}
backup_then_install() {  # backup_then_install MODE SRC DEST
  local mode=$1 src=$2 dest=$3
  [[ -f $src ]] || { echo "  missing source: $src" >&2; return 1; }
  if [[ -f $dest ]] && ! cmp -s "$src" "$dest" && [[ ! -e $dest.pre-mseries ]]; then
    run sudo cp -p "$dest" "$dest.pre-mseries"
  fi
  run sudo install -Dm"$mode" "$src" "$dest"
}

step_wifi() {
  backup_then_install 755 "$repo/mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix" /usr/sbin/mseries-wifi-resume-fix
  if ! lsmod | awk '$1 == "brcmfmac" {found = 1} END {exit !found}'; then
    echo "  brcmfmac is not loaded: loading it (this is what brings Wi-Fi back)"
    run sudo modprobe brcmfmac
  fi
  run sudo systemctl reset-failed omarchy-wifi-resume-fix.service
}
step_power() {
  # The old unit's multi-user.target link is what closed the ordering cycle; remove it before reinstalling.
  run sudo systemctl disable mseries-power.service
  run bash "$repo/mseries/install-power.sh"
  run sudo systemctl daemon-reload
}
step_polkit() {
  backup_then_install 644 "$repo/mseries/netspeed/netusage/49-mseries-netusage.rules" /etc/polkit-1/rules.d/49-mseries-netusage.rules
}
step_greeter() {
  run sudo bash "$repo/mseries/install-greeter-obex-fix.sh"
  run sudo systemctl daemon-reload
}
step_wattmeter() {
  run sudo apt-get install -y git meson ninja-build valac gettext libgtop2-dev libudev-dev libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnotify-dev
  run bash "$repo/mseries/install-battery-eta.sh"
}

[[ $dry -eq 1 ]] && echo "DRY RUN: nothing will be changed." || { echo "Applying: ${only[*]}"; sudo -n true 2>/dev/null || sudo -v; }
for step in "${only[@]}"; do
  echo "== $step"
  if ! "step_$step"; then failures+=("$step"); echo "  step $step FAILED; continuing" >&2; fi
done

echo "== check"
if [[ $dry -eq 1 ]]; then
  echo "  (skipped in dry run)"
else
  lsmod | awk '$1 == "brcmfmac" {f = 1} END {print "  brcmfmac loaded: " (f ? "yes" : "NO")}'
  echo "  failed units now:"; systemctl --failed --no-legend 2>/dev/null | sed 's/^/    /' || true
  echo "  mseries-power links: $(ls /etc/systemd/system/*.target.wants/mseries-power.service 2>/dev/null | tr '\n' ' ')"
  echo "  (polkit prompts: confirm with: journalctl -b -t polkit-agent-helper-1 --since '30 min ago' --no-pager)"
fi
if [[ ${#failures[@]} -gt 0 ]]; then echo "Failed steps: ${failures[*]}" >&2; exit 1; fi
echo "Done."
