# Machine Lab user guide

Machine Lab runs other operating systems on this Mac with QEMU. ARM64 (aarch64) machines run under KVM at near-native
speed. x86-64 / amd64 machines are supported too, but only by **software emulation**: no hardware acceleration, so they are
far slower than ARM64 guests (a small Alpine ISO boots to a login prompt in under a minute; a full desktop takes much longer). Every x86-64 machine is labelled "emulated" and shows a warning.

## Install

```sh
bash mseries/install-machine-lab.sh        # builds, installs to ~/.local and pins it in the dock
bash mseries/machine-lab/build-deb.sh      # or build machine-lab_<version>_arm64.deb (runs the tests first)
```

Needs QEMU (`qemu-system-arm`, `qemu-utils`), UEFI firmware (`qemu-efi-aarch64`) and access to `/dev/kvm`.
The Overview tab's setup check tells you which of these is missing and how to fix it.

## Machines

- **YOUR MACHINES** are installed guests, including any managed with `mseries/vms/mseries-vm` (`~/vms/*/vm.conf`),
  which Machine Lab finds on its own.
- **NEW: NOT INSTALLED** are machines that have not been installed yet. New Machine (Ctrl+N) offers presets: Omarchy
  (can download and install itself), elementary OS (uses an ARM64 ISO already downloaded by mseries-vm), Ubuntu, Debian,
  Fedora, or a blank machine for any ARM64 `.iso`.
- Each machine has Overview, Display, Console and Settings tabs. Settings (CPUs, memory, disk, SSH port, colour) are
  locked while it runs; the disk size is fixed once the disk exists.

## Display

Starting a machine opens its Display tab: the guest's screen at about 30 fps with its own mouse and keyboard.

| Action | How |
| --- | --- |
| Send the keyboard and mouse to the machine | click the screen |
| Give them back | Ctrl+Alt+G, or Release Keyboard in full screen |
| Full screen | F11, the button under the screen, or Ctrl+Alt+F (works while the machine has the keyboard) |
| Leave full screen | F11, Ctrl+Alt+F, or the Exit Full Screen button that appears when the pointer reaches the top |
| Ctrl+Alt+Del | the button under the screen |
| Screenshot | camera button, saved to Pictures |

Other shortcuts: Ctrl+N new machine, F5 or Ctrl+R re-check disk space and requirements, Ctrl+Q quit (running
machines are stopped).

**Clipboard (text).** Settings, "Share clipboard" (off by default). It applies the next time the machine starts, and the guest needs the
SPICE agent (`spice-vdagent`; the elementary OS image already has it). What works today: copy in the guest, paste on the Mac. Copy on the
Mac and paste in the guest is not working yet (see `experiments/clipboard/README.md`). Images, files and drag-and-drop are not supported by
QEMU's clipboard channel yet (issue #264).

## Snapshots (restore points)

Open a machine's Settings tab and use **Snapshots** to save a restore point of its disk before an upgrade or an experiment.
Shut the machine down first: a snapshot saves the disk, not the running memory. **Restore…** rolls the disk back to that point
(everything done since is lost, so it asks first) and the bin icon deletes a snapshot. Names may use letters, numbers, dots, dashes
and underscores. Snapshots live inside the machine's `disk.qcow2` and grow it as the machine changes; deleting the machine removes
them. They are not a backup: if the disk file is lost, so are they. Not available for guests managed by `mseries-vm`.

## Incus containers and VMs

Machine Lab lists your Incus instances in the sidebar under "INCUS · CONTAINERS AND VMS", next to its own machines, so
containers and VMs are managed in one place. It uses the `incus` command (your user needs the `incus-admin` group and the Incus
service running: `sudo systemctl start incus`).

- **See:** state, address, memory in use, image, snapshots and processor limit, refreshed every few seconds.
- **Act:** Start, Stop (graceful, then forced if the guest ignores it), Restart, Pause and Resume, Open Terminal (an `incus exec`
  shell in Terminal), Delete (asks first, removes the instance and its snapshots), and a Log tab with the console log.
- **Create:** New Machine, "Incus container or VM…": pick a name, Container or Virtual machine, an image (Ubuntu, Debian,
  Alpine, Fedora, Arch or any image alias such as `images:alpine/edge`) and optional CPU and memory limits. Containers share this
  Mac's kernel and start in seconds; Incus VMs run their own kernel under KVM. Instances here are ARM64, like the host.
- Incus VMs do not get the Display tab yet (use the Log tab or Open Terminal).

## x86-64 (emulated) machines

Pick one of the "(x86-64)" presets or "Blank x86-64". They need `qemu-system-x86` and `ovmf` (the Overview setup check says so) and
no KVM. Expect long installs and boots: give them 2 CPUs, and use an ARM64 machine whenever the guest has an ARM64 build. Use an
amd64 installer ISO. Clipboard sharing and the Display tab work the same way; Windows on x86-64 is not set up here.

## Installing a system

1. Pick the preset. Omarchy: use **Download and Install** (checks the latest ARM64 nightly, verifies its SHA-256 and
   installs unattended; the sign-in is shown and saved with owner-only permissions). Any other system: choose or drop
   an ARM64 `.iso`, then **Start Installer**.
2. Install in the Display tab. When the guest shuts down after a real install, Machine Lab detaches the installer and
   boots the disk from then on.
3. **Windows 11 ARM64** needs extra steps (virtio-win drivers, a 64 GB disk, `GPU=ramfb`): see
   `mseries/OS9-HANDOFF.md`, "Windows 11 ARM64 installed and first-booted".

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "No access to /dev/kvm" | add your user to the `kvm` group and log in again |
| Low disk space warning | machine disks grow as the guest writes; free space or shrink the disk in Settings, then press F5 |
| Display stays black | the guest may use a kernel without a graphics driver for QEMU's virtual GPU; see the Console tab. elementary OS images default to the Apple-only Fairydust kernel, which does not boot on QEMU (see the handoff) |
| `mseries-vm` commands hang | they should not: the Display uses its own `qmp-view.sock`. Guests started before that socket existed hold the control socket while the Display tab is open; restart them |
| Keys dropped in the Windows installer | type slowly or use the Browse tree; WinPE loses fast input |

## macOS

macOS guests cannot run on Linux here. The "macOS (experimental)" page runs real probes and shows how each route fails.
See `ROADMAP.md`.
