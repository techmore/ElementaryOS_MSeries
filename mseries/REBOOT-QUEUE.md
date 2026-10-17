# Reboot queue — what is staged and what each reboot unlocks

Updated 2026-10-17. This page exists because the work had spread across
`ROADMAP.md`, `fairydust/usb4/*` and `gala-drawers/HANDOFF.md`, and the question
"what is actually waiting for a reboot right now?" had no single answer.

Everything below is **already installed/staged**. Nothing here needs building.
The cost is only the reboot itself.

## Two kinds of "reboot" — don't confuse them

| Kind | What it restarts | Unlocks | Cost |
|---|---|---|---|
| **Relogin** (logout/login) | Gala + the session | Drawers plugin, hotkeys, patched compositor | ~20 s, no kernel change |
| **Kernel boot** | Everything, on a chosen kernel | A different kernel's features (Touch ID, DP-IN experiments) | Full reboot, GRUB menu choice |

The drawer/dock work is **kernel-independent** — it rides along with either
kernel, so a relogin can be folded into a kernel boot if you want to save a cycle
(you then can't tell which change caused a problem, so don't do that for a first
test).

## The queue, in order

| # | Reboot | Unlocks | Kernel | Risk |
|---|---|---|---|---|
| 1 | Relogin | Drawers + dock integration (see below) | unchanged | Low — stock Gala/dock fall back automatically |
| 2 | Kernel boot, **dock detached** | Touch ID / SEP (Aurora kernel) | `7.1.12-2-20261015.19-sep-ARCH` | Low — every other GRUB entry still boots |
| 3 | Kernel boot, dock attached | The DCP firmware question (DP-IN) | `7.1.13-elementary-fairydust-usb4-dptunnel` | Low, but low expected value — see below |

Do **1** first. It is the only one that is guaranteed to produce a visible result.

---

### 1. Relogin — drawers, hotkeys, dock integration

Already live in this session: the **patched dock** (chevron + Command-drag) is
running, so those need nothing.

Waiting on a Gala restart:

- Drawers plugin — rebuilt from source and installed (the previously installed
  `.so` predated the assign feature; it had no OSD support at all).
- Hotkeys — reset to `Control+N` to toggle, `Control+Alt+N` to assign.
  (Left Command is `Control` on this keyboard; `Super+N` is the dock's own.)
- gschema — the installed copy was missing `assign-1..9`; reinstalled and
  recompiled. All 18 keys are now set.
- Settings app — installed as **Drawer Shortcuts**.

**After logging back in:**

```bash
bash mseries/check-drawers.sh      # everything should be green
```

Then, by hand: `Control+1` / `Control+2` (Terminal, Tasks), `Control+Alt+1` with
an app focused (assigns it, with an on-screen confirmation), the chevron at the
end of the dock (5 slots, arrow reveals 4; drag an app onto one), and hold
`Control` + drag the dock to slide it along the bottom edge.

Config is `~/.config/mseries/gala-drawers.ini` — INI edits apply **live**, no
restart. Only the gsettings hotkeys need the Gala restart.

**Revert:** `bash mseries/install-dock-drawers.sh --revert` and
`bash mseries/install-gala-screen-corners.sh --disable` — both take effect at the
next login.

**Known gap:** the dock's slide offset is held in memory, so it resets to centred
when the dock restarts. Persisting it needs a settings key on the dock's
(system-wide) schema.

### 2. Kernel boot — Touch ID / SEP (Aurora)

Kernel `7.1.12-2-20261015.19-sep-ARCH` (from `omacom/linux-aurora`, commit
`5ec1028c`), GRUB entry **`elementary OS (Aurora SEP kernel - Touch ID test)`**.

**Fixed this session:** the initramfs that shipped with it was an Arch
`mkinitcpio` image with **no hooks at all** — no `cryptsetup`, no LVM, no
busybox — so it dropped straight into the initramfs shell. It has been rebuilt
from the known-good image with the Aurora kernel's modules. The broken original
is kept at
`/var/backups/initrd.img-7.1.12-2-20261015.19-sep-ARCH.arch-no-hooks-20261017-085537`.

**Before you boot:** detach the dock. Not because of any documented requirement —
because this kernel drives DP-IN tunnels by default (`dp_display=1`), and the
entry sets `thunderbolt.dprx_timeout=15000`, so a dock that doesn't answer can
stall the boot by up to 15 s and confound the result. Keep keyboard and mouse
plugged into the Mac itself, or you'll be stuck at the GRUB menu.

**After boot:**

```bash
uname -r                                                     # expect ...-sep-ARCH
systemctl status apple-sep.path apple-sep.service
ls -la /dev/sep-bio
journalctl -k | grep -i sep
sudo systemctl start fprintd && fprintd-list "$USER"
sudo aurora-touchid-setup                                    # enroll; needs a finger
```

**Still open:** which PAM service the lock screen uses, so `pam_fprintd` can be
wired into it. sudo and polkit are handled by the setup script.

**Blocker, now pinned down (2026-10-17):** the SEP driver matches
`compatible = "apple,sep"` and ships device-tree nodes for t8103 (M1), t602x (M2),
t8112, t8122 and t8140 — but **not for t6000/t6001/t6002** (M1 Pro/Max/Ultra).
This machine is `apple,j314s` / `apple,t6000`, so the driver binds to nothing and
never publishes `/dev/sep-bio`. The `integration/aurora` branch tip is the release
merge for this exact build, so there is nothing newer to wait for. Everything on
the userspace side is already in place; the only missing piece is the device-tree
node. Full analysis, the node template, and what addresses are still needed:
[`aurora-touchid-state.md`](aurora-touchid-state.md).

**Note on this entry's cmdline:** it uses the *fairydust* DP-IN parameter names
(`thunderbolt.allow_dp_tunnel`, `thunderbolt.dprx_bypass`). Those don't exist on
this kernel — two of the three args are silently ignored, and Aurora has no
`dprx_bypass` equivalent at all. Aurora's own knobs are
`thunderbolt_apple.dp_display`, `.dpin_aux` and `.dpin_mode_value`. Harmless for
a dock-less boot; fix the entry before testing DP-IN on this kernel.

### 3. Kernel boot — the DCP firmware question (DP-IN)

**Deliberately not armed.** The diagnostic for the current blocker is already
compiled into
`initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img` (verified: 14
`DPINDBG` sites in `appledrm.ko`), but `next_entry` is empty — arming it would
hijack reboot #1, and no `dmesg | grep DPINDBG` output has ever been captured.

When you want it:

```bash
sudo grub-reboot elementary-usb4-dpin-controlled    # then reboot
sudo dmesg | grep DPINDBG
```

**What it decides:** the DP-IN activation gate already clears (HPD high,
INACTIVE-ACK handshake passes, crossbar routes). The failure is one layer up —
`DP source preparation failed: -110`, the DCP firmware never completing
`linkcfg_completion`, i.e. it never sends `set_active_lane_count`. If `DPINDBG`
confirms that, what remains is reverse-engineering Apple's display firmware,
which upstream describes as work "that is not done yet". That is the decision
point, not a bug.

---

## What does **not** need a reboot

This is the part worth knowing, because it changes how the DP-IN work iterates.

Every file the DP-IN series touches is a **loadable module**:

| Module | Size |
|---|---|
| `thunderbolt.ko` | 8.1 M |
| `thunderbolt_apple.ko` | 492 K |
| `appledrm.ko` | 508 K |
| `phy-apple-atc.ko` | 68 K |
| `phy-apple-dptx.ko` | 28 K |

So Thunderbolt and PHY iterations are `rmmod` + `modprobe` — no machine reboot.
The evidence log already has a module-only rebuild (`hpd-fix-tested-module-only-rebuild`).
Caveat: reloading `appledrm` restarts the display, and on these entries appledrm
registers *after* Gala, which has caused session crashes — so DRM-side changes
still want a session restart, but tunnel/PHY changes do not.

**gsettings** changes to drawer hotkeys need a Gala restart; the drawer **INI**
applies live.

## Live patching (Ksplice / Splice) — why it isn't the answer here

Asked 2026-10-17. Two independent reasons:

1. **Not enabled in this kernel.** `CONFIG_LIVEPATCH` and `CONFIG_KGRAFT` are
   both unset in `fairydust/usb4/config`. The prerequisites are there
   (`CONFIG_FTRACE=y`, `CONFIG_FUNCTION_TRACER=y`, `CONFIG_KPROBES=y`), but the
   framework is not compiled in — enabling it means rebuilding the kernel, i.e.
   the reboot you were trying to avoid.
2. **Wrong tool for these changes anyway.** Live patching replaces *functions*
   in an already-loaded kernel. The DP-IN series adds new source files
   (`dpin.c`, `apple-dpin-state.c`), new Kconfig symbols and new module
   parameters. Live patching cannot add a module or a parameter — it can only
   swap the body of a function that already exists.

Historically: Splice was the x86-only MIT research prototype; Ksplice was its
Oracle product, and the free desktop tier was discontinued. On Ubuntu the only
supported option is Canonical Livepatch, which covers *stock Canonical kernels*
and security fixes only — not locally built kernels like these.

The practical equivalent for this project is the module reload above, which the
DP-IN work already uses.
