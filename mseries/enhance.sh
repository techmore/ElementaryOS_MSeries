#!/bin/bash
# Install the M-series enhancements into an elementary root, without a running
# session: it only writes files and plants systemd enable symlinks, so it works
# against a chroot / mounted subvolume (transform/elementary-grow.sh runs it at
# build time) or against the live system.
#
#   mseries/enhance.sh [--root DIR] [--only a,b] [--skip a,b] [--list]
#
# Modules (all on by default; each is idempotent and independent):
#   tuning    zram swap (zstd, half of RAM), zswap off, ModemManager off, AppCenter
#             background daemon not autostarted for new users
#   power     battery charge limit (80%) + lower CPU ceiling on battery, with the
#             polkit action the Quick Settings switch uses
#   audio     WirePlumber rules (speaker/headphone outputs stay open, no pop; headset
#             mic is not the default) and an audio watchdog that restarts PipeWire
#             when it stops answering
#   session   per-user helpers as system-wide user units: docked-lid mode, GNOME
#             brightness compatibility, ambient keyboard lighting, deferred
#             CodexBar/netusage/Widevine setup in the desktop user session
#   theme     softer accent colours and larger window corners for new users
#   payload   the scripts, patches and sources the first-boot job needs
#   firstboot a one-shot job that, on the first boot with network, installs native
#             Brave, the Touchegg gesture daemon and the patched panel/shell
#             components (see mseries/enhance-firstboot.sh)
#
# Not enabled automatically, on purpose (each changes how the desktop behaves in
# a way people disagree about, or carries a risk of its own):
#   Command/Ctrl key swap + Command+Space launcher (mseries/apply-desktop-settings.py),
#   rounded screen corners (replaces the compositor for the session:
#   mseries/install-gala-screen-corners.sh), the Asahi speaker DSP chain
#   (mseries/install-pipewire-lv2.sh then install-audio-stack.sh --with-dsp).
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=/
only=""
skip=""
ALL=(tuning power audio session theme payload firstboot)

log() { printf '[enhance] %s\n' "$*"; }

while (( $# )); do
  case $1 in
    --root) ROOT=${2:?--root needs a directory}; shift ;;
    --only) only=${2:?--only needs a list}; shift ;;
    --skip) skip=${2:?--skip needs a list}; shift ;;
    --list) printf '%s\n' "${ALL[@]}"; exit 0 ;;
    -h | --help) sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ -d $ROOT ]] || { echo "no such root: $ROOT" >&2; exit 1; }
R=${ROOT%/}

want() {
  local m=$1
  [[ ,$skip, != *,$m,* ]] || return 1
  [[ -z $only || ,$only, == *,$m,* ]]
}

# put MODE DEST < content        write DEST (under the root) atomically-ish
put() {
  local mode=$1 dest=$R$2
  mkdir -p "$(dirname "$dest")"
  cat >"$dest"
  chmod "$mode" "$dest"
}

# copy MODE SRC DEST
copy() { install -D -m "$1" "$2" "$R$3"; }

# Enable units by planting symlinks; never starts anything.
enable() {
  local flag=()
  [[ $1 == --global ]] && { flag=(--global); shift; }
  systemctl --root="${ROOT}" "${flag[@]}" enable "$@" >/dev/null 2>&1 ||
    log "could not enable $* (unit missing in this root?); continuing"
}

# ---------------------------------------------------------------------------
mod_tuning() {
  put 0644 /etc/systemd/zram-generator.conf <<'EOF'
# ElementaryOS_MSeries: compressed swap in RAM
[zram0]
zram-size = ram / 2
max-zram-size = 8192
compression-algorithm = zstd
swap-priority = 100
EOF
  put 0644 /etc/sysctl.d/99-mseries-zram.conf <<'EOF'
# ElementaryOS_MSeries: tuning for zram-backed swap (no disk seek cost, so swap eagerly, no read-ahead)
vm.swappiness = 100
vm.page-cluster = 0
EOF
  put 0644 /etc/tmpfiles.d/mseries-zswap.conf <<'EOF'
# ElementaryOS_MSeries: zram already compresses swap
w /sys/module/zswap/parameters/enabled - - - - 0
EOF
  # This Mac has no modem.
  systemctl --root="${ROOT}" disable ModemManager.service >/dev/null 2>&1 || true
  # AppCenter's background daemon (~680 MB resident) is not started for new
  # accounts; AppCenter itself still works.
  put 0644 /etc/skel/.config/autostart/io.elementary.appcenter.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=AppCenter (background updates disabled)
Hidden=true
EOF
  log "tuning: zram swap, zswap off, ModemManager off, AppCenter daemon off for new users"
}

mod_power() {
  copy 0755 "$here/power/mseries-power" /usr/local/sbin/mseries-power
  copy 0644 "$here/power/org.techmore.mseries.power.policy" /usr/share/polkit-1/actions/org.techmore.mseries.power.policy
  put 0644 /etc/systemd/system/mseries-power.service <<'EOF'
[Unit]
Description=Apply battery charge limit and power-source CPU policy
After=power-profiles-daemon.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/mseries-power apply

[Install]
WantedBy=graphical.target
EOF
  put 0644 /etc/udev/rules.d/80-mseries-power.rules <<'EOF'
# Plugging or unplugging the charger re-applies the policy.
SUBSYSTEM=="power_supply", KERNEL=="macsmc-ac", ACTION=="change", TAG+="systemd", ENV{SYSTEMD_WANTS}+="mseries-power.service"
EOF
  enable mseries-power.service
  log "power: 80% charge limit and battery CPU policy (change with: sudo mseries-power limit 100)"
}

mod_audio() {
  copy 0644 "$here/audio/asahi-audio-no-suspend.conf" /etc/wireplumber/wireplumber.conf.d/50-mseries-asahi-no-suspend.conf
  copy 0644 "$here/audio/asahi-headset-mic.conf" /etc/wireplumber/wireplumber.conf.d/50-mseries-asahi-headset-mic.conf
  copy 0755 "$here/audio/audio-watchdog.py" /usr/libexec/mseries/audio-watchdog
  put 0644 /usr/lib/systemd/user/mseries-audio-watchdog.service <<'EOF'
[Unit]
Description=Restart the audio stack when it stops responding (Apple Silicon)
ConditionPathExists=/proc/device-tree/compatible

[Service]
ExecStart=/usr/bin/python3 -I /usr/libexec/mseries/audio-watchdog
Restart=on-failure
RestartSec=10
Nice=10

[Install]
WantedBy=default.target
EOF
  enable --global mseries-audio-watchdog.service
  log "audio: WirePlumber no-suspend/headset-mic rules and the audio watchdog"
}

mod_session() {
  local lib=/usr/libexec/mseries
  # A compiled system database is ignored unless the user profile selects it.
  local profile=$R/etc/dconf/profile/user
  mkdir -p "$(dirname "$profile")"
  if [[ ! -f $profile ]]; then
    printf 'user-db:user\n' >"$profile"
  fi
  if ! grep -qxF 'system-db:local' "$profile"; then
    printf '\nsystem-db:local\n' >>"$profile"
  fi
  put 0644 /etc/dconf/db/local.d/00-mseries-brightness <<'EOF'
# Avoid automatic display brightness changes on M-series elementary installs.
# Users can still override these defaults from their desktop settings.
[org/gnome/settings-daemon/plugins/power]
ambient-enabled=false
idle-dim=false
EOF
  if [[ -x $R/usr/bin/dconf ]]; then
    if [[ $ROOT == / ]]; then
      "$R/usr/bin/dconf" update || log "could not compile the system dconf defaults"
    elif command -v chroot >/dev/null 2>&1; then
      chroot "$ROOT" /usr/bin/dconf update || log "could not compile the system dconf defaults in $ROOT"
    fi
  fi
  copy 0755 "$here/docked-lid/mseries-docked-lid" $lib/docked-lid
  copy 0755 "$here/brightness/shell-bridge.py" $lib/brightness-bridge
  copy 0755 "$here/keyboard-backlight/backlight.py" $lib/keyboard-backlight

  put 0644 /usr/lib/systemd/user/mseries-docked-lid.service <<EOF
[Unit]
Description=Docked lid mode: lock instead of suspend while a USB4 dock is attached
ConditionPathExists=/proc/device-tree/compatible

[Service]
ExecStart=/usr/bin/python3 -I $lib/docked-lid
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=default.target
EOF
  enable --global mseries-docked-lid.service

  # These two need the compositor's D-Bus services, so they start from the
  # desktop session (an autostart entry) and retry until Gala is up.
  put 0644 /usr/lib/systemd/user/mseries-brightness-bridge.service <<EOF
[Unit]
Description=Pantheon compatibility for GNOME brightness management

[Service]
ExecStart=/usr/bin/python3 $lib/brightness-bridge
Restart=on-failure
RestartSec=5
EOF
  put 0644 /usr/lib/systemd/user/mseries-keyboard-backlight.service <<EOF
[Unit]
Description=Ambient keyboard lighting for elementary OS

[Service]
ExecStart=/usr/bin/python3 $lib/keyboard-backlight
Restart=on-failure
RestartSec=10
EOF
  local unit
  for unit in brightness-bridge keyboard-backlight; do
    put 0644 /etc/xdg/autostart/mseries-$unit.desktop <<EOF
[Desktop Entry]
Type=Application
Name=M-series $unit
OnlyShowIn=Pantheon;
Exec=systemctl --user start mseries-$unit.service
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
  done
  copy 0755 "$here/user-enhance.sh" $lib/user-enhance
  put 0644 /usr/lib/systemd/user/elementary-mac-user-enhance.service <<EOF
[Unit]
Description=Install per-user M-series desktop enhancements
ConditionPathExists=$lib/user-enhance

[Service]
Type=oneshot
ExecStart=/bin/bash $lib/user-enhance

[Install]
WantedBy=default.target
EOF
  put 0644 /usr/lib/systemd/user/elementary-mac-user-enhance.timer <<'EOF'
[Unit]
Description=Retry per-user M-series enhancements until prerequisites are ready

[Timer]
OnBootSec=2min
OnUnitInactiveSec=5min
Unit=elementary-mac-user-enhance.service

[Install]
WantedBy=timers.target
EOF
  put 0644 /usr/lib/systemd/user/elementary-mac-user-enhance.path <<'EOF'
[Unit]
Description=Set up DRM after Brave creates a user profile

[Path]
PathChanged="%h/.config/BraveSoftware/Brave-Browser/Local State"
Unit=elementary-mac-user-enhance.service

[Install]
WantedBy=default.target
EOF
  enable --global elementary-mac-user-enhance.path
  enable --global elementary-mac-user-enhance.timer
  log "session: docked-lid, brightness, keyboard lighting and deferred per-user enhancements"
}

mod_theme() {
  copy 0644 "$here/theme/gtk-4.0.css" /etc/skel/.config/gtk-4.0/gtk.css
  copy 0644 "$here/theme/gtk-3.0.css" /etc/skel/.config/gtk-3.0/gtk.css
  log "theme: softer accents and window corners for new users"
}

# What the first-boot job runs: the install scripts, their helper library, the
# patches and sources. Laid out as <prefix>/mseries/... because the scripts find
# their data relative to the directory above themselves.
mod_payload() {
  local prefix=/usr/share/elementary-mac f
  for f in lib-backup.sh lib-apt.sh install-brave.sh install-video-decode.sh video-decode/90-mseries-avd.conf install-native-firefox.sh install-touchegg.sh \
           install-network-throughput.sh install-quick-settings-brightness.sh \
           install-sound-indicator-fix.sh install-keyboard-indicator-fix.sh \
           install-files-portal-fix.sh install-gala-osk-fix.sh install-netusage-policy.sh \
           install-codexbar.sh install-brave-widevine.sh codexbar-opencode-local.py \
           codexbar-opencode-wrapper.py user-enhance.sh \
           netspeed/netusage/install.sh netspeed/netusage/netusage.py \
           netspeed/netusage/netusage.service netspeed/netusage/49-mseries-netusage.rules \
           quick-settings/ScreenBrightness.vala quick-settings/KeyboardBrightness.vala \
           quick-settings/ChargeLimit.vala quick-settings/AudioOutputModel.vala quick-settings/AudioOutput.vala \
           gala-daemon-fix/build.py \
           netspeed/panel-network.patch netspeed/wire-network-usage.py; do
    copy 0755 "$here/$f" "$prefix/mseries/$f"
  done
  for f in "$here"/patches/*.patch; do
    copy 0644 "$f" "$prefix/mseries/patches/$(basename "$f")"
  done
  # sudo is a no-op for root; the scripts were written for a user account.
  put 0755 $prefix/shim/sudo <<'EOF'
#!/bin/sh
# Run the command; the first-boot job is already root.
while [ "${1#-}" != "$1" ]; do shift; done
exec "$@"
EOF
}

mod_firstboot() {
  copy 0755 "$here/enhance-firstboot.sh" /usr/sbin/elementary-mac-enhance
  put 0644 /usr/lib/systemd/system/elementary-mac-enhance.service <<'EOF'
[Unit]
Description=elementary OS (M-series) first-boot enhancements
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/elementary-mac/enhance/finished

[Service]
Type=oneshot
ExecStart=/usr/sbin/elementary-mac-enhance --run
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=infinity

[Install]
WantedBy=multi-user.target
EOF
  enable elementary-mac-enhance.service
  log "firstboot: Brave, hardware video decode, user-app dependencies, DNS policy and panel patches install with network (log: /var/log/elementary-mac-enhance.log)"
}

for m in "${ALL[@]}"; do
  if want "$m"; then "mod_$m"; else log "skipping $m"; fi
done
log "done (root: ${ROOT})"
