# fairydust DP-Alt-Mode kernel — build kit (Asahi Arch / omarchy)

Builds a **`linux-asahi-fairydust`** kernel that adds the experimental
USB-C **DisplayPort Alt Mode** support, installed *beside* stock
`linux-asahi` so GRUB keeps a rescue entry.

- Upstream code: Asahi's [`fairydust`](https://github.com/AsahiLinux/linux/tree/fairydust) branch.
- Packaging adapted from Grzegorz Smajdor's Asahi-Arch kit
  (<https://grzegorzsmajdor.com/blog/2026-omarchy-asahi-arch-m1/>), GPL-2.0.
- Context / evidence: `../USB-C-DOCK-DP-ALT-MODE.md`.

## Hardware coverage (important)

The fairydust DT patches bless **one** USB-C port per machine. From the
branch commit `t60xx: j[34]1[46]: Add dp-altmode hacks`:

> Blessed dp-altmode port is **front left** port on j314/j316/j414/j416.

So this Mac (`apple,j314s`, MBP 14" M1 Pro) is covered — put the dock on
the **front-left** USB-C port.

## Files

| File | What it does |
| --- | --- |
| `PKGBUILD` | builds `linux-asahi-fairydust`, pinned to Asahi `7.1.13-3` (this machine's stock), distinct `localversion` so it coexists |
| `build-and-install.sh` | preflight (aarch64, Arch, ≥35 GiB) → deps → `makepkg` → install → initramfs → `update-m1n1` → GRUB |
| `verify.sh` | run after booting fairydust: one OK/FAIL per hardware block |

## One file you must generate (not redistributable)

```bash
# kernel config — from the machine's stock linux-asahi
zcat /proc/config.gz > config
```

The `PKGBUILD` fetches the Asahi **`fairydust` branch snapshot** directly
(no patch to apply), so `config` is the only input. This sidesteps the
version-pin drift of patch-based builds: at the time of writing the branch
is 12 commits ahead / 2 behind `asahi-7.1.13-3`.

(If you prefer the pinned-release + `fairydust.patch` route — the original
kit's — see the blog linked at the top; generate the patch with
`git diff asahi-7.1.13-3...origin/fairydust`.)

## Run it

Reboot into **Omarchy (Arch)** first — the build needs `pacman`,
`makepkg`, `update-m1n1`, and `mkinitcpio`, none of which exist in the
elementary subvolume. Then, as your normal user (not root):

```bash
sudo ./build-and-install.sh        # sudo is used only for pacman/install
```

Budget **1–3 hours** and **~35 GiB** of scratch, and stay on AC.

## After first boot

1. In GRUB choose the **fairydust** entry.
2. Plug the dock into the **front-left** USB-C port.
3. `./verify.sh` should print `OK` for "DisplayPort connector".
4. To boot *elementary* on this kernel, add a GRUB entry pointing the
   elementary menuentry's `linux` at
   `/vmlinuz-linux-asahi-fairydust` + its initramfs (the stock elementary
   entry keeps using the stock kernel).

## Host-side build (from the elementary subvolume)

Booting Omarchy just to build is avoidable: `host/` chroots into the Arch
(`@`) subvolume from elementary.

| File | What it does |
| --- | --- |
| `host/fairydust-build.sh` | runs on elementary as root; mounts the `@` subvol + a **private tmpfs `/run`** (so the live Wayland session is never touched), provisions chroot DNS, drops the kit in and chroots to the driver |
| `host/fairydust-driver.sh` | runs inside the chroot as root; installs deps, `makepkg`, installs the package, builds initramfs, `update-m1n1`, `grub-mkconfig` |

Two chroot gotchas the scripts handle (both cost a failed run to discover):

- **Private `/run` hides the resolver.** `/etc/resolv.conf` is a symlink to
  `/run/systemd/resolve/stub-resolv.conf`; with a fresh tmpfs `/run` that
  target is gone, so `pacman` can't resolve any mirror. The build script
  recreates the target on the tmpfs with public resolvers first.
- **This network is flaky for bursty lookups.** `getent` succeeds while
  `pacman`'s libcurl concurrently gets `Could not resolve host`. The driver
  wraps every network step (`pacman`, `rustup`, `makepkg`) in a retry loop.

Run it:

```bash
sudo host/fairydust-build.sh        # ~1-3h; see /tmp/opencode/fairydust-build.log
```

Then reboot and pick the fairydust entry in GRUB (dock on the FRONT-LEFT
USB-C port) and run `./verify.sh`.

## Safety

- Stock `linux-asahi` stays installed; GRUB lists both. A bad boot is one
  menu entry away.
- `update-m1n1` rewrites the shared `/boot/m1n1/boot.bin` (device tree) —
  this affects **both** OSes. Run `verify.sh` before trusting it.
- The version pin is deliberate. When stock `linux-asahi` moves past
  `7.1.13-3`, bump `_rcver`/`_asahirel` in the PKGBUILD, regenerate
  `fairydust.patch`, and expect the patch to need rework.
