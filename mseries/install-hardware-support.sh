#!/usr/bin/env bash
# Stage diagnostics without starting services or touching hardware.
# --enable-bluetooth: opt-in recovery on FUTURE suspends, after failure qualification.
# --keyboard-keys: opt-in F4/F5/F6 remapping, effective after reboot/replug.
# --root DIR: offline image root; default / uses sudo when needed.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=/
bluetooth=0
keyboard=0
remove=0
offline=0
arguments=("$@")
while (( $# )); do
  case $1 in
    --root) root=${2:?--root needs a directory}; offline=1; shift ;;
    --enable-bluetooth) bluetooth=1 ;;
    --keyboard-keys) keyboard=1 ;;
    --uninstall) remove=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
[[ $root == /* && -d $root ]] || { echo 'Root must be an existing absolute directory' >&2; exit 2; }
root=$(cd -- "$root" && pwd -P)
if [[ $root == / && $EUID != 0 ]]; then
  exec sudo bash "$here/install-hardware-support.sh" "${arguments[@]}"
fi
if [[ $root == / && $remove == 0 && $offline == 0 ]]; then
  # Offline staging never runs apt. Manual post-install gets its runtime tools.
  if ! dpkg-query -W -f='${Status}\n' bluez dbus-bin libnotify-bin pciutils rfkill 2>/dev/null | awk '
      $0 != "install ok installed" { bad=1 } END { exit bad }'; then
    apt-get install -y bluez dbus-bin libnotify-bin pciutils rfkill
  fi
fi
put() {
  local dest=${root%/}/$3
  mkdir -p "$(dirname "$dest")"
  install -m "$1" "$here/$2" "$dest"
}
link() {
  local dest=${root%/}/$2
  # An administrator mask or replacement wins over a vendor default.
  if [[ ! -e $dest && ! -L $dest ]]; then
    mkdir -p "$(dirname "$dest")"
    ln -s "$1" "$dest"
  fi
}
if (( remove )); then
  for file in usr/bin/mseries-hw-apple-silicon \
    usr/share/applications/mseries-power-report.desktop \
    usr/libexec/mseries/power-report usr/libexec/mseries/sleep-cost \
    usr/libexec/mseries/bluetooth-supported usr/libexec/mseries/bluetooth-resume-fix \
    usr/libexec/mseries/peripherals usr/lib/systemd/user/mseries-peripherals.service \
    usr/lib/systemd/system-sleep/mseries-sleep-cost \
    usr/lib/systemd/user/mseries-sleep-cost.service \
    usr/lib/systemd/system/mseries-bluetooth-resume-fix.service \
    etc/udev/hwdb.d/90-mseries-keyboard.hwdb; do
    rm -f "${root%/}/$file"
  done
  # Only remove enable/command links this installer owns. Keep admin masks,
  # regular launchers and replacement links that staging deliberately preserved.
  for pair in \
    'usr/bin/mseries-power-report|../libexec/mseries/power-report' \
    'usr/lib/systemd/user/graphical-session.target.wants/mseries-sleep-cost.service|../mseries-sleep-cost.service' \
    'usr/bin/mseries-peripherals|../libexec/mseries/peripherals' \
    'usr/lib/systemd/user/graphical-session.target.wants/mseries-peripherals.service|../mseries-peripherals.service' \
    'etc/systemd/system/suspend.target.wants/mseries-bluetooth-resume-fix.service|/usr/lib/systemd/system/mseries-bluetooth-resume-fix.service'; do
    file=${root%/}/${pair%%|*}
    if [[ -L $file && $(readlink "$file") == "${pair#*|}" ]]; then rm "$file"; fi
  done
  echo 'Removed support files. Historical energy records are retained. Log out/reboot before checking removal.'
  exit 0
fi
put 755 hardware/mseries-hw-apple-silicon usr/bin/mseries-hw-apple-silicon
put 755 power/sleep_cost.py usr/libexec/mseries/sleep-cost
put 755 power/power_report.py usr/libexec/mseries/power-report
put 644 hardware/mseries-power-report.desktop usr/share/applications/mseries-power-report.desktop
link ../libexec/mseries/power-report usr/bin/mseries-power-report
put 755 power/mseries-sleep-cost-hook usr/lib/systemd/system-sleep/mseries-sleep-cost
put 644 power/mseries-sleep-cost.service usr/lib/systemd/user/mseries-sleep-cost.service
link ../mseries-sleep-cost.service usr/lib/systemd/user/graphical-session.target.wants/mseries-sleep-cost.service
put 755 hardware/peripherals.py usr/libexec/mseries/peripherals
put 644 hardware/mseries-peripherals.service usr/lib/systemd/user/mseries-peripherals.service
link ../libexec/mseries/peripherals usr/bin/mseries-peripherals
link ../mseries-peripherals.service usr/lib/systemd/user/graphical-session.target.wants/mseries-peripherals.service
put 755 hardware/bluetooth-supported usr/libexec/mseries/bluetooth-supported
put 755 hardware/bluetooth-resume-fix usr/libexec/mseries/bluetooth-resume-fix
put 644 hardware/mseries-bluetooth-resume-fix.service usr/lib/systemd/system/mseries-bluetooth-resume-fix.service
put 644 power/LICENSE.omacom usr/share/doc/mseries-hardware-support/LICENSE.omacom
put 644 power/UPSTREAM.md usr/share/doc/mseries-hardware-support/UPSTREAM.md
if (( bluetooth )); then
  link /usr/lib/systemd/system/mseries-bluetooth-resume-fix.service etc/systemd/system/suspend.target.wants/mseries-bluetooth-resume-fix.service
fi
if (( keyboard )); then
  put 644 hardware/90-mseries-keyboard.hwdb etc/udev/hwdb.d/90-mseries-keyboard.hwdb
  # Compile only inside the explicitly selected root; no trigger on live devices.
  systemd-hwdb --root="$root" update
fi
echo 'Support files staged; no service started or hardware changed. New user units apply at next login.'
