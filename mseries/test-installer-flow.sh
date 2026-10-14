#!/usr/bin/env bash
# Simulates the whole bin/elementary-mac-setup flow in a sandbox, without touching
# the machine: every external tool is a shim that records its call, the machine's
# state (boot layout, encryption, kernel command line) is a set of files the test
# flips between steps, and the grow / unlock / Asahi tools are stubs that log what
# they were asked to do. It checks what the real run would DO and in what order:
# the state machine, the reboots between steps, what is passed to each tool, the
# files the installer writes, resumability, and the failure paths.
#
# It cannot show that the real tools work on hardware - only that the installer
# drives them correctly.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/.." && pwd)
sandbox=$(mktemp -d /tmp/elementary-flow-test.XXXXXX)
cleanup() { [[ $sandbox == /tmp/elementary-flow-test.* ]] && find "$sandbox" -delete; }
trap cleanup EXIT

fails=0
check() { # check NAME CONDITION...
  local name=$1; shift
  if "$@"; then :; else echo "FAIL: $name" >&2; fails=$((fails + 1)); fi
}
calls=$sandbox/calls.log
: >"$calls"

# --- shims for every external tool the flow can reach ------------------------
shim=$sandbox/bin
mkdir -p "$shim"
for tool in pacman systemctl grub-mkconfig mkinitcpio loadkeys setfont hostnamectl localectl \
            systemd-firstboot grub-mkfont btrfs sleep; do
  printf '#!/bin/sh\necho "%s $*" >>"%s"\nexit 0\n' "$tool" "$calls" >"$shim/$tool"
  chmod +x "$shim/$tool"
done
export PATH=$shim:$PATH

# --- stub repo checkouts: the tools the installer drives ----------------------
src=$sandbox/state/src
tools=$sandbox/state/omarchy-tools
mkdir -p "$src/.git" "$src/transform" "$src/mseries/boot" "$tools/.git" "$tools/bin"
cat >"$src/transform/elementary-grow.sh" <<EOF
#!/bin/bash
echo "grow \$* hostname=\${ELEMENTARY_HOSTNAME:-} enhance=\${ELEMENTARY_ENHANCE:-} hash=\${ELEMENTARY_PASSWORD_HASH:+set}" >>"$calls"
[[ -f "$sandbox/grow-fails" && \$1 == --apply ]] && exit 1
exit 0
EOF
printf '#!/bin/bash\necho "unlock-screen $*" >>"%s"\n' "$calls" >"$src/mseries/install-unlock-screen.sh"
printf '#!/bin/bash\necho "snippet $*" >>"%s"\n' "$calls" >"$src/mseries/boot/mkinitcpio-snippet"
printf '#!/bin/bash\necho "boot-to-esp $*" >>"%s"\n' "$calls" >"$tools/bin/omarchy-system-boot-to-esp"
printf '#!/bin/bash\necho "btrfs-migrate $*" >>"%s"\n' "$calls" >"$tools/bin/omarchy-system-btrfs-migrate"
chmod +x "$src"/transform/*.sh "$src"/mseries/*.sh "$src"/mseries/boot/* "$tools"/bin/*

# --- the machine: state the test flips between steps ---------------------------
machine=$sandbox/machine
mkdir -p "$machine"
set_machine() { # set_machine SEPARATE_BOOT ENCRYPTED CMDLINE_HAS_CRYPTDEVICE
  echo "$1" >"$machine/sep"; echo "$2" >"$machine/enc"
  if [[ $3 == 1 ]]; then
    echo "BOOT_IMAGE=/vmlinuz-linux-asahi root=UUID=abc rw cryptdevice=UUID=def:root:allow-discards" >"$machine/cmdline"
  else
    echo "BOOT_IMAGE=/vmlinuz-linux-asahi root=UUID=abc rw" >"$machine/cmdline"
  fi
}
fake_mnt=$sandbox/elementary-root
mkdir -p "$fake_mnt/usr/share/plymouth/themes/elementary"
: >"$fake_mnt/usr/share/plymouth/themes/elementary/elementary.plymouth"
printf '### BEGIN\nmenuentry '"'"'elementary OS (M-series, 7.1)'"'"' --id elementary-mseries {\n}\n' >"$sandbox/grub.cfg"
printf 'GRUB_DEFAULT=0\nGRUB_SAVEDEFAULT=true\n' >"$sandbox/grub-defaults"
printf '#!/bin/sh\nexec tail -n +3 $0\nmenuentry x {\n    linux /vmlinuz root=UUID=abc rw\n}\n' >"$sandbox/40_elementary-grow"

# run_step_in_sandbox [extra assignments...]: one resumed step, as a unit would run it.
run_flow() {
  (
    # shellcheck source=/dev/null
    source "$repo/bin/elementary-mac-setup"
    # shellcheck disable=SC2034  # these are read by the sourced installer
    STATE_DIR=$sandbox/state; SRC=$src; TOOLS_SRC=$tools
    INSTALLED_MARKER=$STATE_DIR/installed; GROWN_MARKER=$STATE_DIR/grown
    CONF=$sandbox/setup.conf; SELF=$sandbox/self; UNIT=$sandbox/unit.service
    GRUB_DEFAULTS=$sandbox/grub-defaults; GRUB_CFG=$sandbox/grub.cfg
    GRUB_ENTRY=$sandbox/40_elementary-grow; PACMAN_HOOK_DIR=$sandbox/hooks
    CMDLINE_FILE=$machine/cmdline
    # Machine state and every system-touching helper, replaced by the sandbox.
    boot_is_separate() { [[ $(cat "$machine/sep") == 1 ]]; }
    root_is_encrypted() { [[ $(cat "$machine/enc") == 1 ]]; }
    root_source() { echo /dev/sandbox; }
    have_network() { return 0; }
    quiet_console() { :; }
    restore_printk() { :; }
    mount_elementary() { ELEMENTARY_MNT=$fake_mnt; }
    unmount_elementary() { ELEMENTARY_MNT=""; }
    elementary_exists() { [[ -f $sandbox/partial-build ]]; }
    install_initramfs_fixes() { echo "initramfs-fixes" >>"$calls"; }
    reboot_now() { echo "REBOOT: $1" >>"$calls"; }
    want_encrypt=1 username=alice hostname=box keymap=us password_hash='$6$salt$hash' keep_default=0 enhance=1 \
      repo=techmore/ElementaryOS_MSeries ref=main forge=github.com
    for assignment in "$@"; do eval "$assignment"; done
    save_conf
    load_conf
    run_step "$(current_step)"
  ) >>"$sandbox/out.log" 2>&1
}
calls_since() { sed -n "$(( $1 + 1 )),\$p" "$calls"; }
mark() { wc -l <"$calls"; }
has() { grep -qF -- "$1" <<<"$2"; }

# 1. A fresh machine with encryption wanted: boot layout comes first, then a reboot.
set_machine 0 0 0
m=$(mark); run_flow; out=$(calls_since "$m")
check "step 1 runs boot-to-esp --yes" has "boot-to-esp --yes" "$out"
check "step 1 reboots" has "REBOOT" "$out"
check "step 1 does not encrypt yet" bash -c '! grep -q btrfs-migrate <<<"$1"' _ "$out"

# 2. Boot moved: encryption is staged with the initramfs fixes, then a reboot.
set_machine 1 0 0
m=$(mark); run_flow; out=$(calls_since "$m")
check "step 2 installs initramfs fixes first" has "initramfs-fixes" "$out"
check "step 2 stages encryption" has "btrfs-migrate --encrypt --yes" "$out"
check "step 2 reboots" has "REBOOT" "$out"

# 3. Encrypted, but this boot's kernel line has no cryptdevice=: reboot once, build nothing.
set_machine 1 1 0
m=$(mark); run_flow; out=$(calls_since "$m")
check "reboots once for the unlock parameters" has "REBOOT: Encryption finished" "$out"
check "does not build on the old command line" bash -c '! grep -q "^grow" <<<"$1"' _ "$out"
check "records that it already rebooted" test -f "$sandbox/state/cmdline-reboot"
# ...and if the new boot still lacks it, stop with a clear failure instead of looping.
m=$(mark)
if run_flow; then check "second attempt without cryptdevice fails" false; else :; fi
check "second attempt does not reboot again" bash -c '! grep -q REBOOT <<<"$1"' _ "$(calls_since "$m")"
check "failure says what to check" grep -q "no cryptdevice=" "$sandbox/out.log"

# 4. Encrypted with the right command line: the full elementary step.
set_machine 1 1 1
m=$(mark); run_flow; out=$(calls_since "$m")
check "builds with --apply" has "grow --apply" "$out"
check "passes the hostname" has "hostname=box" "$out"
check "passes the enhancement switch" has "enhance=1" "$out"
check "creates the account from the stored hash (not the password)" has "grow --finalize alice hostname= enhance= hash=set" "$out"
check "marks the build finished" test -f "$sandbox/state/grown"
check "logs the owner in automatically" grep -q "autologin-user=alice" "$fake_mnt/etc/lightdm/lightdm.conf.d/50-elementary-mac-autologin.conf"
check "session is pantheon" grep -q "autologin-session=pantheon" "$fake_mnt/etc/lightdm/lightdm.conf.d/50-elementary-mac-autologin.conf"
check "installs the unlock screen from the new root" has "unlock-screen --theme-from $fake_mnt/usr/share/plymouth/themes/elementary" "$out"
check "kernel-sync pacman hook targets the Asahi kernels" grep -q "Target = linux-asahi\*" "$sandbox/hooks/90-elementary-sync-kernel.hook"
check "kernel-sync hook runs --sync-kernel" grep -q "elementary-grow.sh --sync-kernel" "$sandbox/hooks/90-elementary-sync-kernel.hook"
check "makes elementary the default entry by id" grep -q '^GRUB_DEFAULT="elementary-mseries"' "$sandbox/grub-defaults"
check "no saved default overrides it" grep -q '^GRUB_SAVEDEFAULT=false' "$sandbox/grub-defaults"
check "splash requested on the elementary entry" grep -q "quiet splash" "$sandbox/40_elementary-grow"
check "regenerates grub.cfg" has "grub-mkconfig" "$out"
check "writes the installed marker" test -f "$sandbox/state/installed"
check "retires its resume config" test ! -e "$sandbox/setup.conf"
check "reboots into elementary" has "REBOOT: elementary OS installed" "$out"
# Order matters: the build comes before the boot setup that depends on it.
order=$(grep -nE "^grow --apply|^grow --finalize|^unlock-screen|^REBOOT: elementary" <<<"$out" | cut -d: -f2 | cut -d' ' -f1-2 | tr '\n' '|')
check "steps happen in order (apply, finalize, unlock screen, reboot)" test "$order" = "grow --apply|grow --finalize|unlock-screen --theme-from|REBOOT|"

# 5. Finished: nothing left to do (and the answers file is gone, so it says done).
( source "$repo/bin/elementary-mac-setup"; [[ $(next_step 1 1 1 1) == done ]] ) ||
  { echo "FAIL: next_step after install is not done" >&2; fails=$((fails + 1)); }

# 6. An interrupted earlier build is rolled back first; a finished one is kept.
rm_state() { find "$sandbox/state" -maxdepth 1 \( -name grown -o -name installed -o -name cmdline-reboot \) -delete; }
rm_state; : >"$sandbox/partial-build"; set_machine 1 1 1
m=$(mark); run_flow; out=$(calls_since "$m")
first=$(grep -E "^grow" <<<"$out" | head -1)
check "an unfinished @elementary is rolled back before the build" has "grow --rollback" "$first"
rm_state; : >"$sandbox/state/grown"; : >"$sandbox/partial-build"
m=$(mark); run_flow; out=$(calls_since "$m")
check "a finished build is not rebuilt or rolled back" bash -c '! grep -qE "^grow (--apply|--rollback)" <<<"$1"' _ "$out"
check "...but the boot setup still runs" has "unlock-screen" "$out"

# 7. A failed build stops the run, leaves no finished marker, and keeps the config for the next boot.
rm_state; find "$sandbox" -maxdepth 1 -name partial-build -delete; : >"$sandbox/grow-fails"
m=$(mark)
if run_flow; then check "a failed build fails the unit" false; fi
check "no finished marker after a failed build" test ! -e "$sandbox/state/grown"
check "no reboot after a failed build" bash -c '! grep -q "REBOOT: elementary" <<<"$1"' _ "$(calls_since "$m")"
find "$sandbox" -maxdepth 1 -name grow-fails -delete

# 8. --no-encrypt skips boot layout and encryption entirely; --no-enhancements is passed on.
rm_state; set_machine 0 0 0
m=$(mark); run_flow 'want_encrypt=0' 'enhance=0'; out=$(calls_since "$m")
check "no boot-to-esp without encryption" bash -c '! grep -q boot-to-esp <<<"$1"' _ "$out"
check "no unlock screen without encryption" bash -c '! grep -q "^unlock-screen" <<<"$1"' _ "$out"
check "initramfs fixes still applied on the unencrypted path" has "initramfs-fixes" "$out"
check "enhancements switched off reach the build" has "enhance=0" "$out"

if (( fails )); then
  echo "$fails flow check(s) failed; output of the last runs:" >&2
  tail -40 "$sandbox/out.log" >&2
  exit 1
fi
echo "installer flow: all checks passed"
