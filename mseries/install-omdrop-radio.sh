#!/usr/bin/env bash
# AirDrop radio side for the j314s (BCM4387): the root helpers from netmojo-systems/omdrop-awdl (mseries/omdrop-awdl).
# NO kernel change: Aurora's brcmfmac (integration/aurora) already carries the AWDL vendor command and netdev code;
# this installs only the userspace that creates awdl0 and opens a bounded visibility window.
#
#   install-omdrop-radio.sh preflight    read-only checks, no root (default)
#   install-omdrop-radio.sh install      sudo: install helpers and enable the idle awdl0 setup service
#   install-omdrop-radio.sh uninstall    sudo: remove exactly what install put there (and destroy awdl0 if present)
#
# install creates awdl0 as an idle, unmanaged interface and enables that setup at boot.
# It does NOT enable AWDL or open a visibility window; only an explicit `omdrop on` does that.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/omdrop-awdl"
lib=/usr/lib/omdrop
version=0.10.0   # omdrop-awdl package version the radio hooks report (PROVENANCE.md)
files_list=/usr/lib/omdrop/.mseries-installed-files

say() { printf '%s\n' "$*"; }
fail=0
check() { # description, command...
  local d=$1; shift
  if "$@" >/dev/null 2>&1; then say "ok    $d"; else say "FAIL  $d"; fail=1; fi
}
warn() { say "WARN  $*"; }

preflight() {
  say "== hardware"
  local model; model=$(tr -d '\0' </sys/firmware/devicetree/base/model 2>/dev/null)
  say "      model: ${model:-unknown}"
  local id; id=$(lspci -nn 2>/dev/null | grep -o '14e4:44[0-9a-f][0-9a-f]' | head -1)
  say "      wifi pci id: ${id:-none}"
  case "$id" in
    14e4:4433) say "ok    BCM4387: same chip as the upstream-verified 16-inch M1 Pro (send + receive, Everyone and Contacts Only)" ;;
    14e4:4425|14e4:4434) say "ok    ${id}: listed by upstream as receive-verified only" ;;
    *) say "FAIL  no Apple Broadcom Wi-Fi found"; fail=1 ;;
  esac
  say "== kernel driver (no module is replaced)"
  local ko="/lib/modules/$(uname -r)/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko"
  local parms; parms=$(modinfo -F parm "$ko"* 2>/dev/null || true)
  check "running brcmfmac has the AWDL switch (awdl=1 creates via the vendor command)" grep -q '^awdl:' <<<"$parms"
  check "running brcmfmac has awdl_trace (the data-path gate counts tx completions with it)" grep -q '^awdl_trace:' <<<"$parms"
  if [ -r /sys/module/brcmfmac/parameters/awdl ]; then
    [ "$(cat /sys/module/brcmfmac/parameters/awdl)" = 1 ] && say "ok    awdl=1 in the loaded module" || { say "FAIL  awdl is 0 in the loaded module (vendor command not registered)"; fail=1; }
  fi
  say "      loaded firmware: $(journalctl -k -b --no-pager 2>/dev/null | grep -o 'Firmware: BCM4387.*' | tail -1)"
  say "== Wi-Fi interface and NetworkManager (awdl-up refuses a randomised MAC)"
  local sta=; local n
  for n in /sys/class/net/*; do n=${n##*/}; [ "$n" = awdl0 ] && continue; [ -d "/sys/class/net/$n/phy80211" ] && { sta=$n; break; }; done
  say "      infrastructure interface: ${sta:-none}"
  [ -n "$sta" ] && check "$sta carries its permanent MAC (addr_assign_type 0)" test "$(cat /sys/class/net/$sta/addr_assign_type 2>/dev/null)" = 0
  check "NetworkManager scan MAC randomisation is off" bash -c 'grep -rhs "wifi.scan-rand-mac-address" /etc/NetworkManager/conf.d /usr/lib/NetworkManager/conf.d /etc/NetworkManager/NetworkManager.conf | grep -q "=no"'
  if nmcli -g 802-11-wireless.cloned-mac-address connection show --active 2>/dev/null | grep -q -E 'random|stable'; then warn "an active Wi-Fi profile randomises its MAC (cloned-mac-address); awdl-up will refuse"; fail=1; fi
  say "== receiver prerequisites"
  check "python3 + libarchive module (apt: python3-libarchive-c)" python3 -c 'import libarchive'
  check "keyctl (apt: keyutils)" command -v keyctl
  check "polkit (pkexec)" command -v pkexec
  say "== state"
  if ip link show awdl0 >/dev/null 2>&1; then say "      awdl0 exists"; else say "      awdl0 does not exist yet (expected before the first test step)"; fi
  if [ -x "$lib/omdrop-discoverable" ]; then say "      helpers installed in $lib"; else say "      helpers not installed"; fi
  [ $fail = 0 ] && say "PREFLIGHT OK" || say "PREFLIGHT HAS FAILURES (see FAIL lines)"
  return $fail
}

need_root() { [ "$(id -u)" = 0 ] || exec sudo -- "$0" "$@"; }

do_install() {
  need_root install
  preflight || { say "Refusing to install: preflight failed." >&2; exit 1; }
  [ -f "$src/userspace/omdrop-discoverable" ] || { say "vendored sources missing: $src" >&2; exit 1; }
  # Never take ownership of another package's helpers or system configuration.
  # A prior install must be explicitly uninstalled before replacing its manifest.
  local existing
  for existing in "$lib" /usr/share/polkit-1/actions/org.omarchy.omdrop.policy /usr/lib/systemd/system/awdl0.service /usr/lib/NetworkManager/conf.d/99-awdl-unmanaged.conf; do
    if [ -e "$existing" ] || [ -L "$existing" ]; then
      say "Refusing to overwrite $existing; inspect/uninstall the existing installation first." >&2
      exit 1
    fi
  done
  install -d -m755 "$lib" "$lib/radio"
  : > "$files_list"
  put() { install -D -m"$1" "$2" "$3" && echo "$3" >> "$files_list"; }
  put 755 "$src/userspace/omdrop-discoverable" "$lib/omdrop-discoverable"
  put 644 "$src/userspace/omdrop-broadcom.sh" "$lib/omdrop-broadcom.sh"
  local hook
  for hook in up identity tick peer-watch peers diag read trace; do put 755 "$src/userspace/radio/$hook" "$lib/radio/$hook"; done
  sed "s/@VERSION@/$version/" "$src/userspace/radio/probe" > "$lib/radio/probe" && chmod 755 "$lib/radio/probe" && echo "$lib/radio/probe" >> "$files_list"
  put 755 "$src/userspace/awdl-up" "$lib/awdl-up"
  local h
  for h in awdl-airdrop-adv awdl-election awdl-mdns-respond awdl-peer-watch awdl-peers awdl-stats ble-airdrop-adv brcm_iovar mkpsf awdl-af-parse airdrop-send; do
    put 755 "$src/userspace/$h.py" "$lib/$h.py"
  done
  put 755 "$src/userspace/send-to-peer" "$lib/send-to-peer"
  put 755 "$src/userspace/awdl-resolve" "$lib/awdl-resolve"
  put 644 "$src/userspace/awdl_identity.py" "$lib/awdl_identity.py"
  put 644 "$src/userspace/awdl_debug.py" "$lib/awdl_debug.py"
  put 644 "$src/packaging/org.omarchy.omdrop.policy" /usr/share/polkit-1/actions/org.omarchy.omdrop.policy
  put 644 "$src/packaging/awdl0.service" /usr/lib/systemd/system/awdl0.service
  put 644 "$src/packaging/99-awdl-unmanaged.conf" /usr/lib/NetworkManager/conf.d/99-awdl-unmanaged.conf
  systemctl daemon-reload
  if systemctl is-active --quiet NetworkManager; then nmcli general reload conf; fi
  systemctl enable --now awdl0.service
  say "Installed $(wc -l < "$files_list") files and enabled awdl0.service."
  say "awdl0 is configured but idle: AirDrop is not visible until you explicitly turn receiving on."
}

do_uninstall() {
  need_root uninstall
  [ -f "$files_list" ] || { say "No mseries installation manifest; nothing removed."; return; }
  systemctl disable --now awdl0.service 2>/dev/null || true
  if ip link show awdl0 >/dev/null 2>&1 && [ -x "$lib/brcm_iovar.py" ]; then
    local sta; sta=$(for n in /sys/class/net/*; do n=${n##*/}; [ "$n" = awdl0 ] && continue; [ -d "/sys/class/net/$n/phy80211" ] && { echo "$n"; break; }; done)
    [ -n "$sta" ] && timeout --foreground 15 python3 "$lib/brcm_iovar.py" -i "$sta" awdl-if destroy || true
  fi
  if [ -f "$files_list" ]; then
    while IFS= read -r f; do rm -f -- "$f"; done < "$files_list"
    rm -f "$files_list"
    rmdir "$lib/radio" "$lib" 2>/dev/null || true
  fi
  systemctl daemon-reload
  say "Removed everything install placed. The driver and your Wi-Fi settings were never changed."
}

case "${1:-preflight}" in
  preflight) preflight ;;
  install) do_install ;;
  uninstall) do_uninstall ;;
  *) say "usage: $0 [preflight|install|uninstall]" >&2; exit 2 ;;
esac
