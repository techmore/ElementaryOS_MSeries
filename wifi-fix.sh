#!/usr/bin/env bash
# One-shot Wi-Fi diagnose + fix for elementary OS on Apple Silicon.
# Usage: sudo bash wifi-fix.sh ["SSID"]
# Report is saved to /boot/efi/wifi-report.txt (readable from macOS) and ~/wifi-report.txt.
SSID="$1"
OUT=/tmp/wifi-report.txt
exec > >(tee "$OUT") 2>&1
step() { printf '\n===== %s =====\n' "$*"; }

step "kernel / chip"
uname -r; lspci -nn 2>/dev/null | grep -i -E 'broadcom|14e4'

step "firmware present?"
ls -la /lib/firmware/brcm/ 2>&1 | grep -E '4378|4387|total|No such'
systemctl status mseries-wifi-firmware --no-pager 2>&1 | head -15

step "rfkill"
rfkill list

step "driver messages"
dmesg | grep -i -E 'brcmfmac|firmware.*brcm|wlan' | tail -30

step "NetworkManager state"
nmcli general status; nmcli device status

step "fix 1: unblock + reload driver"
rfkill unblock all
modprobe -r brcmfmac_wcc 2>/dev/null; modprobe -r brcmfmac 2>/dev/null
sleep 2; modprobe brcmfmac; sleep 4
systemctl restart NetworkManager; sleep 4
nmcli device status

step "fix 2: rescan"
nmcli radio wifi on
nmcli device wifi rescan 2>&1; sleep 4
nmcli -f IN-USE,SSID,SECURITY,SIGNAL device wifi list

if [ -n "$SSID" ]; then
  step "fix 3: drop stale profile and rejoin '$SSID'"
  nmcli connection delete "$SSID" 2>&1
  nmcli device wifi connect "$SSID" 2>&1
  sleep 5
  nmcli device status
  step "internet / captive portal check"
  ip -br a
  curl -sS -m 8 -o /dev/null -w 'neverssl http=%{http_code} redirect=%{redirect_url}\n' http://neverssl.com 2>&1
fi

step "recent NetworkManager log"
journalctl -b -u NetworkManager -u wpa_supplicant --no-pager 2>/dev/null | tail -50

cp "$OUT" /boot/efi/wifi-report.txt 2>/dev/null && echo "Saved to /boot/efi/wifi-report.txt"
cp "$OUT" "${SUDO_USER:+/home/$SUDO_USER}/wifi-report.txt" 2>/dev/null
echo "Done."
