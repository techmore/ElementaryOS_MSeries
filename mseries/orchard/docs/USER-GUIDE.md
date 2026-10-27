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

Starting a machine opens its Display tab: the guest's screen with its own mouse and keyboard. Machine Lab takes the picture from
QEMU's D-Bus display, which pushes only what changed (an idle machine costs nothing); if that is not available it falls back to
polling about 30 times a second. The guest's own pointer shape is shown as the pointer over the screen.

**Screen size.** By default the machine's screen follows the Display tab: resize the window, or go full screen, and about half a
second after you stop, the guest is asked for that size (a multiple of 8, between 640x480 and 7680x4320). This needs a virtual monitor
that can change size (virtio-gpu, which Machine Lab machines use; the Windows setup framebuffer cannot, and the button turns grey). The
button next to full screen turns it off, in which case the machine keeps its current size and the picture is scaled to fit. The guest
desktop has to react to a monitor change; GNOME and elementary OS do. Not yet confirmed on a live guest.

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

**Clipboard (text, both ways).** Settings, "Share clipboard" (off by default). It applies the next time the machine starts, and the guest needs
the SPICE agent (`spice-vdagent`; the elementary OS image already has it). With it on, text you copy in the machine can be pasted here and
the other way round. Two switches under it, "Paste from this computer into the machine" and "Copy from the machine to this computer", turn
a direction off or on immediately, for all machines (stored in `~/.config/machine-lab/settings.ini`). Text over 1 MiB is not transferred.
Notes: after the guest agent (re)connects, for example when you log in, the text currently on your clipboard is offered to the guest again;
the guest sees it only when something there pastes. Images, files and drag-and-drop are not supported by QEMU's clipboard channel (issue #264).
Host to guest was verified against QEMU's and spice-vdagent's source and a fake-QEMU test suite; it has not yet been confirmed on a live guest
(see `experiments/clipboard/README.md`).

## Ready-made images (skip the installer)

Every Mac here is Apple Silicon, so an ARM64 disk set up on one works on the others. On a new machine, **Or start from a
ready-made image → Use an Image…** loads a bootable disk instead of running an installer. It accepts `.qcow2`, `.img`, `.raw`,
`.vmdk`, `.vdi`, compressed `.xz`, `.zst` or `.gz` disks, and a UTM `.zip` bundle (the biggest disk inside is used, so the Omarchy
UTM zip works). The image is converted into the machine's own `disk.qcow2`, so the original is never modified.

To make an image, shut a machine down and choose **⋮ → Save Disk as Image…**: it writes a compressed qcow2 you can reuse or hand
to another Mac. Notes:
- The image must boot on its own with UEFI (a bootloader on its EFI partition). Firmware settings are not carried over.
- It keeps the accounts, passwords and SSH host keys of the machine it came from. Change the password on first boot, and do not
  share an image that contains anything private.
- Safety checks: only qcow2, raw, vmdk and vdi are accepted; an image that points at another file on its original computer is
  refused (it could otherwise expose files from this Mac to the guest); and Machine Lab checks free space first.

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
3. **Windows 11 ARM64** needs virtio-win drivers, a 64 GB disk and `GPU=ramfb`. Machine Lab does the driver part for you:
   see "Windows: virtio-win drivers and an unattended install" below. The remaining manual details are in
   `mseries/OS9-HANDOFF.md`, "Windows 11 ARM64 installed and first-booted".

## Windows: virtio-win drivers and an unattended install

Windows Setup does not ship drivers for QEMU's virtual hardware: without the virtio-win drivers it cannot read the installer
disc ("A media driver your computer needs is missing"), and OOBE says "No network drivers found". For a Windows guest created with
`mseries-vm create windows` (it shows up in YOUR MACHINES / NEW), Settings has a **Windows drivers (virtio-win)** card:

1. **Download virtio-win** (about 837 MiB). Nothing is downloaded until you press the button. Machine Lab fetches the pinned
   release 0.1.302 from fedorapeople.org over HTTPS only, writes it to a `.partial` file, and keeps it only if its SHA-256 is
   `303f7ae40dad…7949d` (and its size matches). A mismatch deletes the file and shows the expected and actual checksums; an
   interrupted transfer says so and resumes when you press the button again. The file lives in
   `~/.local/share/machine-lab/cache/virtio-win/`. An ISO you already have at `~/vms/downloads/virtio-win/virtio-win.iso` is used if
   it matches the same checksum, so nothing is downloaded twice.
2. Optionally fill in **Unattended install**:
   - *Local account name and password*: creates that administrator and skips the Microsoft-account page. Leave both empty to choose
     in Setup. The password is written in plain text to the answer-file disc (mode 0600, only you can read it) until you remove it.
   - *Let setup finish without a network or Microsoft account*: also sets `BypassNRO`. Best effort; recent Windows 11 builds may
     still show the network page, where **Next** continues (the driver is installed even if that page says it is not).
   - *Erase and partition the machine's disk without asking*: **off by default.** With it off Setup still asks which disk to use and
     nothing is erased. With it on, Setup wipes the machine's own virtual disk (GPT: 100 MB EFI, 16 MB MSR, NTFS) and installs
     onto it; you are asked to confirm.
3. **Attach Drivers and Answer File.** Machine Lab builds a small disc containing `autounattend.xml` (`genisoimage` is needed),
   then adds it and the verified driver disc to the machine's `EXTRA_MEDIA`, and sets `EXTRA_BUS=usb` (Windows PE reads USB natively)
   and `GPU=ramfb` (the Setup screen renders). Existing `EXTRA_MEDIA` entries are kept. Only a machine that is **not installed and not
   running** is changed; an installed Windows machine is never touched.
4. Start the installer. Setup loads `viostor`, `vioscsi`, `NetKVM` and `vioinput` from the driver disc by itself (the answer file's
   `windowsPE` DriverPaths) and finds the answer file on its own. You still accept Microsoft's licence terms and pick the edition
   and a product key option yourself. During specialize the full set (display `viogpudo`, balloon, serial, RNG, pvpanic) is staged in
   the new system too.
5. After the install, press **Remove Answer File**: it detaches the disc and deletes it (and the password with it).

What it does not do: install the QEMU guest agent or SPICE tools (they are an `.msi`/`.exe` on the driver disc, not drivers), accept
the licence, activate Windows, or touch Windows guests that were not created by `mseries-vm`. Windows 11 amd64 (x86-64) answer files
are generated the same way (`amd64` driver folders) but Machine Lab has no Windows x86-64 preset yet.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "No access to /dev/kvm" | add your user to the `kvm` group and log in again |
| Low disk space warning | machine disks grow as the guest writes; free space or shrink the disk in Settings, then press F5 |
| Display stays black | the guest may use a kernel without a graphics driver for QEMU's virtual GPU; see the Console tab. elementary OS images default to the Apple-only Fairydust kernel, which does not boot on QEMU (see the handoff) |
| `mseries-vm` commands hang | they should not: the Display uses its own `qmp-view.sock`. Guests started before that socket existed hold the control socket while the Display tab is open; restart them |
| Keys dropped in the Windows installer | type slowly or use the Browse tree; WinPE loses fast input. The answer file avoids this for the drivers |
| virtio-win download failed or "Checksum mismatch" | the bad file was deleted; check the connection and press Download again. Nothing is attached until the checksum matches |

## macOS

macOS guests cannot run on Linux here. The "macOS (experimental)" page runs real probes and shows how each route fails.
See `ROADMAP.md`.
