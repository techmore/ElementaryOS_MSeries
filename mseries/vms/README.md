# mseries-vm — ARM64 test VMs for the M1 Pro

`mseries-vm` creates, fetches media for, and runs the guests this project needs for testing:

| Guest | How it is sourced | Status |
| --- | --- | --- |
| elementary OS 9 (ARM64) | the newest successful `daily-9.0.yml` CI artifact, or any ISO you pass | verified booting (see below) |
| Windows 11 ARM64 | UUP dump file set, converted to ISO by the pinned upstream converter | download/convert automated; install not exercised unattended |
| Omarchy 4 (Arch Linux ARM) | the prebuilt `omarchy-arm-utm-v2.zip` UTM image, imported into plain QEMU/KVM | verified booting (see below) |
| macOS | — | **not possible on Linux**, explained by `mseries-vm macos` |

Everything lives under `~/vms` (`MSERIES_VM_DIR` overrides). Nothing here touches host disks; installer media
is attached read-only and networking defaults to QEMU user-mode NAT.

## Requirements

Already installed on this Mac: `qemu-system-aarch64`, `qemu-img`, `swtpm`, and the AAVMF firmware in
`/usr/share/AAVMF`. `mseries-vm info` checks all of that plus `/dev/kvm`.

`fetch windows` installs `aria2 cabextract wimtools chntpw genisoimage` when missing (they are all available
for arm64). `fetch elementary` needs an authenticated `gh` (the repo default is `techmore/ElementaryOS_MSeries`).

## Quick start

```bash
cd ~/ElementaryOS_MSeries

# elementary OS installer
./mseries/vms/mseries-vm fetch elementary
./mseries/vms/mseries-vm create elementary
./mseries/vms/mseries-vm start elementary            # or --headless

# Omarchy 4 from the archive.org UTM image
./mseries/vms/mseries-vm import-omarchy ~/vms/downloads/omarchy-arm-utm-v2.zip
./mseries/vms/mseries-vm start omarchy --headless
./mseries/vms/mseries-vm screenshot omarchy          # read the PNG, no display needed

# Windows 11 ARM64 (TPM 2.0 + Secure Boot, NVMe disk)
./mseries/vms/mseries-vm fetch windows               # ~5 GB UUP set, resumable
./mseries/vms/mseries-vm fetch windows --convert     # builds the ISO (upstream converter, pinned)
./mseries/vms/mseries-vm create windows --iso ~/vms/downloads/windows-uup/*.iso
./mseries/vms/mseries-vm start windows

# The honest answer about macOS guests
./mseries/vms/mseries-vm macos
```

## Command reference

| Command | Purpose |
| --- | --- |
| `info` | host prerequisites and capabilities |
| `list` / `status NAME` | VM inventory and run state |
| `create elementary [name] [--iso PATH] [--memory MiB] [--cpus N] [--disk GiB] [--boot iso\|disk]` | new Linux-ish VM |
| `create windows [name] --iso PATH [...]` | new Windows VM (TPM 2.0, Secure Boot, NVMe by default) |
| `import-omarchy IMAGE.zip [--name NAME] [--delete-source]` | UTM bundle → plain qcow2 + `vm.conf` |
| `start NAME [--headless [--daemon]] [--force]` | boot it (GTK window, or none + QMP) |
| `stop NAME [--force]` | graceful ACPI powerdown, then TERM, then KILL |
| `wait NAME --pattern REGEX [--timeout SEC]` | block until the serial log matches (scripting) |
| `serial NAME [-n N]` | tail the serial log |
| `screenshot NAME [FILE.png]` | QMP screendump (works headless) |
| `key NAME QCODE [...]` | send guest keystrokes via QMP, e.g. `key NAME ret` (GRUB, installers) |
| `snapshot NAME save\|restore\|delete\|list [tag]` | qcow2 snapshots (VM must be stopped) |
| `set NAME KEY VALUE` | tweak `ISO`, `BOOT`, `MEMORY_MB`, `CPUS`, `NET`, `HOSTFWD`, `AUDIO`, `GL`, `TPM`, ... |
| `delete NAME --force` | remove the VM directory |
| `fetch elementary` | newest successful CI artifact + `INSTALLER-SHA256SUMS` check |
| `fetch windows [--convert]` | UUP dump ARM64 set download (+ optional ISO conversion) |
| `macos` | why a macOS guest cannot work here |

Each VM directory contains `vm.conf` (plain `KEY=VALUE`, safe to edit), `disk.qcow2`, `vars.fd` (its own UEFI
variables copy), `qemu.args` (the exact last command line), `serial.log`, and `qemu.log`.

## Windows specifics

`create windows` sets `TPM=on` (swtpm, state in `tpm/`) and `AAVMF_CODE.ms.fd` for Secure Boot —
on ARM the firmware alone enforces Secure Boot; there is no x86-style SMM (and QEMU's `virt`
machine has no `smm` property). The disk is NVMe so the installer needs no virtio driver. `--virtio-media virtio-win.iso` attaches extra
read-only media when you want virtio drivers for network or balloon devices.

The UUP download uses the official JSON API (`api.uupdump.net`) and the converter script from
`git.uupdump.net/uup-dump/converter`, pinned to commit `dbc65de`. Before aria2 is consulted, every local file is
checked against the SHA-256 in `files.json`; only missing or corrupt files are (re-)downloaded, with a fresh URL
from the API. This matters because the signed URL tokens expire: a naive `aria2c --continue` rerun re-hashes
complete files and re-probes expired URLs, drowning in `403`s while doing nothing useful. Conversion runs
locally and needs no Windows machine. The converted ISO is built from Microsoft's own update files, exactly
like the website's "Download and convert to ISO" flow.

## Safety model

- User-mode networking (`-nic user`) by default; `--net none` when the guest must stay offline.
- Installer media attached read-only; only `~/vms/<name>/disk.qcow2` is writable.
- `delete` refuses to run non-interactively without `--force`.
- `stop` escalates gently: ACPI powerdown → SIGTERM → SIGKILL (with a warning).
- Snapshots are qcow2 internal snapshots and require a stopped VM.

## Testing the toolkit itself

```bash
./mseries/vms/test-mseries-vm.sh
```

80 hermetic checks: PATH-stubbed `qemu-system-aarch64`, `swtpm`, `qemu-img`, `gh`, `curl`, `aria2c` and
`git`, a temporary `MSERIES_VM_DIR`, no KVM, no network, no root. CI runs it on every push.

## macOS

See [`../MACOS-VM.md`](../MACOS-VM.md) and `mseries-vm macos`: a macOS guest needs Apple's Virtualization
frameworks and Apple's virtual hardware, which exist only on macOS hosts. The practical options are a remote
Mac, or booting the internal macOS install with `asahi-bless --set-boot-macos`.
