#!/usr/bin/env bash
# Stage offline enhancements; no apt, live services, kernel or bootloader writes.
# Called by apple-silicon finalize while its target dconf binary still exists.
set -euo pipefail
root=${1:?build root required}
stage=${2:?empty staging root required}
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$stage"
# Retain any distribution-selected profile instead of replacing it.
if [[ -f $root/etc/dconf/profile/user ]]; then
    install -Dm644 "$root/etc/dconf/profile/user" "$stage/etc/dconf/profile/user"
fi
bash "$here/enhance.sh" --root "$stage" --only tuning,power,audio,session,theme,payload

# /usr/local is mutable /var/usrlocal on sysupdate and is not in its artifact.
# The factory panel and policy use the same immutable executable instead.
install -Dm755 "$stage/usr/local/sbin/mseries-power" "$stage/usr/libexec/mseries/power"
rm -rf "$stage/usr/local"
mkdir -p "$stage/usr/bin"
ln -s ../libexec/mseries/power "$stage/usr/bin/mseries-power"
sed -i 's|/usr/local/sbin/mseries-power|/usr/libexec/mseries/power|g' \
    "$stage/etc/systemd/system/mseries-power.service" \
    "$stage/usr/share/polkit-1/actions/org.techmore.mseries.power.policy"
# Empty staging roots cannot disable an inherited enabled unit.
ln -s /dev/null "$stage/etc/systemd/system/ModemManager.service"
# Bake the authorization prerequisite; per-user setup must never request sudo.
install -Dm644 "$here/netspeed/netusage/49-mseries-netusage.rules" \
    "$stage/etc/polkit-1/rules.d/49-mseries-netusage.rules"
# Consumers install the matching Qt/runtime package list during image assembly.
printf '%s\n' 'Factory runtime dependencies are declared in both arm64 consumers.' \
    > "$stage/usr/share/elementary-mac/factory-user-deps"

# Compile with the target binary before finalize prunes package payloads. Merge
# distribution local defaults so the compiled database retains their entries.
mkdir -p "$root/tmp"
work=$(mktemp -d "$root/tmp/mseries-dconf.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/local.d"
if [[ -d $root/etc/dconf/db/local.d ]]; then
    cp -a "$root/etc/dconf/db/local.d/." "$work/local.d/"
fi
cp -a "$stage/etc/dconf/db/local.d/." "$work/local.d/"
cp -a "$work/local.d/." "$stage/etc/dconf/db/local.d/"
chroot "$root" /usr/bin/dconf compile "${work#"$root"}/local" "${work#"$root"}/local.d"
install -m644 "$work/local" "$stage/etc/dconf/db/local"

# Recompile persistent /etc after new leaf defaults arrive on image updates.
# Merely copying a compiled database would preserve an older existing database.
cat > "$stage/usr/lib/systemd/system/mseries-desktop-defaults.service" <<'EOF'
[Unit]
Description=Compile M-series desktop defaults before login
After=systemd-tmpfiles-setup.service
Before=display-manager.service
ConditionPathExists=/etc/dconf/db/local.d/00-mseries-brightness

[Service]
Type=oneshot
ExecStart=/usr/bin/dconf update
RemainAfterExit=yes

[Install]
WantedBy=graphical.target
EOF
systemctl --root="$stage" enable mseries-desktop-defaults.service
