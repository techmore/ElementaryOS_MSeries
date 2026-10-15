# Dock-video session — USB4 DisplayPort tunnelling (2026-10-16)

> **Read this box first. It is the whole session in one question.**
>
> Tomorrow has exactly **one** question that can move the frontier, and one
> unambiguous early-stop:
>
> **Does the sink answer?** Attach the dock and look for a completed DPRX read /
> a DCP "sink present" — or the opposite (`INACTIVE_SINK_DETECTED`, `DPRX read
> timeout`, `card2-DP-1: disconnected`).
>
> - **Sink answers** → the host path is proven end to end; continue to the
>   DCP / DPTX / mode-set side (section 2, row 4–5).
> - **Sink stays silent** → **stop, do not start patching the driver.** No code
>   change on this machine can complete a sink read that the router cannot make
>   (`DP-TUNNEL-RE.md` §6.1). Save the evidence, and pivot to the macOS trace
>   (`MACOS-TRACE-RUNBOOK.md`) — the only way to learn the missing "DP IN PHY".
>
> Section 1 is the command sequence, section 2 the go/no-go table, and
> **section 8 lists the things that would waste your day.**

Background and the full reverse-engineering map: [`DP-TUNNEL-RE.md`](DP-TUNNEL-RE.md)
(measured state §5, offline analysis §6, hazard §9). The trace path and its
prerequisites: [`MACOS-TRACE-RUNBOOK.md`](MACOS-TRACE-RUNBOOK.md).

---

## Resume map — where everything lives (2026-10-15)

If this session is lost, this is the fastest way back.

- **Doc branch:** `docs/dock-video-decision`, checked out at
  `/home/sdolbec/wt-dockvideo` — **run the session from there**, not from
  `/home/sdolbec/ElementaryOS_MSeries` (that checkout is on a different branch
  and its collector is stale). The branch holds this runbook, `DP-TUNNEL-RE.md`,
  `boot-dt.py`, `test-dp-tunnel.sh`, the installer (PR #53), **and** the
  experiment-2 kernel implementation (`0002-experimental-dp-tunnel.patch` + the
  matching `debian/build.sh` pin), so a build from this branch reproduces the
  installed kernel. `re/usb4-exp2` is the original implementation branch (same
  patch, sha256 `c962eff0…`).
- **Reinstallable artifact stash:** `/home/sdolbec/dp-tunnel-artifacts/exp2/`
  (exp-2 kernel `.deb`, `fairydust-m1n1-boot.bin`, checksums, build log). No
  download needed to reinstall.
- **Pre-generated tree variants:** `/home/sdolbec/dp-tunnel-artifacts/boot-variants/`
  (`config-A..D.bin` + `MANIFEST.txt`) — the ablation matrix as ready files.
  Regenerate any time: `boot-dt.py --in /boot/m1n1/boot.bin --variants DIR`.
- **Experiment-1 boot evidence:** `/home/sdolbec/dptunnel-logs/`
  (`dmesg-failed-boot.txt`, `journal-failed-boot.txt`, `state-failed-boot.txt`).
- **Live-image backups:** `/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455`
  and `/root/usb4-backup-20261015-140455/boot.bin`.
- **`/tmp` is tmpfs** and does not survive a reboot; keep everything under
  `/home`.

---

## 0. Where we start (all of this is verified, not assumed)

**Installed on the ESP/root right now**

| item | state |
|---|---|
| kernel | `7.1.13-elementary-fairydust-usb4-dptunnel`, GRUB entry `elementary-usb4-dptunnel` (last entry in `/boot/grub/custom.cfg`) |
| source | experiment 2, CI run `38788230910` from `re/usb4-exp2` (`94c6e84`, `dprx_bypass` etc.), `build-kernel` ✅ |
| `vmlinuz` | 13 305 989 B, 2026-10-15 15:23 |
| `initramfs` | 24 421 478 B, 2026-10-15 15:27 — **contains the experiment-2 `appledrm.ko`** (checked by extracting it: one `apple,dp-tunnel` symbol) |
| `/usr/lib/modules/<kv>` | experiment-2 `thunderbolt.ko` (`dprx_bypass` present) and `appledrm.ko` (`apple,dp-tunnel`, `force_link` present); **no `<kv>/<kv>` nesting** |
| device tree in `/boot/m1n1/boot.bin` | j314s DTB #25, 93 217 B, sha256 `353bc857…`: `dcp@28cc00000` `mux-controls` phandle 153 arg **1 (dpin0)**, `mux-index` 2, `apple,dp-tunnel` **present**; HDMI `dcp@289c00000` arg **0** unchanged |
| pre-experiment image | `/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455` (sha256 `5cbc5f30…`), root-only copy in `/root/usb4-backup-20261015-140455/` |
| artifact stash | `/home/sdolbec/dp-tunnel-artifacts/exp2/` (kernel .deb, `fairydust-m1n1-boot.bin`, checksums, build log) — no download needed to reinstall |

**If you ever rebuild locally:** `debian/build.sh` pins the sha256 of
`0002-experimental-dp-tunnel.patch`, and on this branch the pin matches the
committed patch (`c962eff0…`, experiment 2), so a checkout of this branch builds
the kernel that is installed. Otherwise just reinstall from the stash above.

**What experiment 1 achieved (measured 2026-10-15, boot `-2`)**

The crossbar took the new route (`Switched dpin0 to dispext1,0`) and the USB4
connection manager got all the way to a live tunnel — host DP IN `0:5` paired
with a dock DP OUT adapter, 22500 Mb/s allocated in allocation mode, and the
Video / AUX TX / AUX RX paths all reported `activation complete` (4×). Every
attempt then died at the sink's DPCD read: `DPRX read timeout` ×25533 (21479 on
`1:13`, 4054 on `1:14`), with no link rate, no training, no video. No other boot
in the whole persistent journal has ever reached path activation.

**What experiment 2 adds** (all three pieces are already in the installed kernel)

1. `thunderbolt.dprx_bypass` — runtime-writable bool. When set, `tb_dp_wait_dprx()`
   returns immediately, so the tunnel stops waiting for the host router's
   `DP_COMMON_CAP_DPRX_DONE` bit (the experiment-1 wall) and can activate.
2. `apple,dp-tunnel` on `&dcpext1` — the DCP leaves `dptxport[port].atcphy` NULL
   instead of pointing it at `atcphy1`, so link-rate changes never call
   `atcphy_dp_configure(atcphy1)` while that PHY must stay in USB4 mode.
3. `force_link` — a per-connector debugfs handle that calls
   `dcp_dptx_connect()` / `dcp_dptx_disconnect()`. The live DRM connector for
   `dcpext1` is **`card2-DP-1`**, so the handle is
   `/sys/kernel/debug/dri/2/DP-1/force_link` (find it with `find`, below).

Live proof the installed tree is the armed experiment-2 build: the DCP probes as
`DCP index:2 dptx target phy: 1 dptx die: 0 tunnel: 1` (`tunnel: 1` is
experiment 2's own message).

---

## 1. The test, top to bottom

### 1.1 Before you boot: check the arm state (no root needed, no dock needed)

Run everything from the branch that carries the experiment. This worktree is it:

```bash
cd /home/sdolbec/wt-dockvideo     # branch docs/dock-video-decision = the experiment
python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin
```

> Do **not** run from `/home/sdolbec/ElementaryOS_MSeries`: that checkout is on a
> different branch (`codex/guide-collapsed-by-default`) and its
> `test-dp-tunnel.sh` is **stale**. Confirm you are in the right place first —
> `git -C /home/sdolbec/wt-dockvideo branch --show-current` must print
> `docs/dock-video-decision`.

Expect `mux-controls … arg 1 -> dpin0 (ACIO DP IN 0)` and `apple,dp-tunnel:
present`. If either is wrong, stop and fix the tree before spending a reboot.

Boot the **last** GRUB entry (`elementary OS (M-series, fairydust-usb4-dptunnel
test)`). The default entry is untouched on purpose.

### 1.2 After the desktop is up, *before* attaching the dock

```bash
uname -r                                    # 7.1.13-elementary-fairydust-usb4-dptunnel
grep -o 'thunderbolt[^ ]*' /proc/cmdline    # allow_dp_tunnel=1 …

# Arm the DPRX bypass first: this is what stops the 25533-line retry storm and,
# with it, the window in which unplugging the dock wedges the Type-C port.
echo 1 | sudo tee /sys/module/thunderbolt/parameters/dprx_bypass
cat /sys/module/thunderbolt/parameters/dprx_bypass    # 1

# Start a live capture so the bring-up is not lost if the machine misbehaves.
sudo dmesg -w > ~/dptunnel-logs/exp2-live-$(date +%H%M).txt 2>&1 &
```

Put the monitor on the **dock's HDMI** output with the **HDMI→HDMI** cable, turn
the monitor **on and select that input**, then plug the dock into **USB-C Left
Front** (that is `atcphy1`, the port the crossbar and the ACIO are wired to).
The DP→HDMI cable over the dock's DP output is the cross-check for later.

### 1.3 Collect the verdict

```bash
cd /home/sdolbec/wt-dockvideo
bash mseries/fairydust/usb4/test-dp-tunnel.sh 2>&1 | tee ~/dptunnel-logs/test-exp2-$(date +%H%M).txt
```

It prints the arm state, the module parameters, the connector statuses, the
crossbar switches, the last 20 tunnel lines, and a verdict paragraph. Give the
bring-up ~20 s after the dock is attached before believing a "nothing yet".

If the verdict says the DCP has not connected, force it by hand — this path has
never been exercised:

```bash
sudo sh -c 'echo 1 > "$(find /sys/kernel/debug/dri -name force_link | head -1)"'
# then re-run the collector; the tunnel connector is card2-DP-1:
cat /sys/class/drm/card2/card2-DP-1/status
```

Arm the bypass before you touch the cable (see section 4).

---

## 2. Decision tree

Read the collector's counters:

| what you see | what it means | next |
|---|---|---|
| `dcpext1 mux-controls idx 0` | tree not armed | write the tree (section 3), reboot |
| `DPRX bypass engaged 0`, `DPRX read timeout > 100` | bypass not in effect — the storm is the old wall | `echo 1 > …/dprx_bypass`; expect the counter to stop growing |
| `Video/AUX path activation complete > 0` **and** `DPRX bypass engaged > 0` | the tunnel is up on our terms | look for `dcp_dptx_connect(port=0)`, then `force_link`; watch `card2-DP-1/status` |
| `dcp_dptx_connect(port=0) > 0` but no connector | the DCP connected, the sink never answered | this is the sink side: see the two probes below |
| `card2-DP-1 status: connected` | **first light** — link up, EDID over AUX worked | if still black it is now a mode-set problem, not a link problem: check `drm_info` / Gala display settings |
| `activation complete 0` and no `DP IN available` | the CM never paired anything: no live sink on the dock's port | try the dock's other DP/HDMI port (below) |

**Hold the right expectation for `dprx_bypass`.** By the source (`DP-TUNNEL-RE.md`
section 6.1) the bypass only stops the *kernel* waiting: the router's DP IN
adapter still has to fill `DP_LOCAL_CAP` from its own AUX read of the sink. If the
sink never answered, the bypass gets you "tunnel active" but a picture cannot
follow. So treat it as a **fabric probe**, not a fix: "the tunnel reaches
activation complete and the timeout storm stops" is success *for the probe*, and
still expects `card2-DP-1: disconnected`.

The DCP firmware does its own sink detection on the tunnelled path (measured:
`acking unhandled call 20` = `INACTIVE_SINK_DETECTED`, `DP-TUNNEL-RE.md`). The
collector prints a call census, so watch it: calls 5/6/7/9 (link config, link
rate) would mean the firmware is driving the link, which is a far better success
signal than a quiet log.

**Two cheap probes**

1. **Which dock DP OUT adapter is which physical port?** (free). The log only
   ever says `1:13` / `1:14`. Attach the monitor to exactly one dock output at a
   time and note which adapter acks the hotplug (`acking hot plug event on 1:1x`).
   That mapping removes a whole class of confusion, and costs nothing.
2. **Which host DP IN adapter is our dpin0?** (costs a reboot — only if the sink
   answered or you still have time). We route the crossbar to `dpin0` and the CM
   independently picks `0:5`. The `0:5` <-> `dpin0` correspondence is inferred, not
   measured. `boot-dt.py --mux-arg 2` (dpin1) is the cheap test: if `0:6` then
   pairs and behaves the same, the mapping is "5=dpin0, 6=dpin1"; if the crossbar
   route stops mattering, then the crossbar is not in the path at all — a
   genuinely useful negative result.

---

## 3. The ablation matrix (secondary — only after the sink question is answered)

**Deprioritise this.** Each row costs a reboot, and experiment 1 already showed
the host side works. Run it only if the sink answers and you still have time; it
will not produce a picture by itself.

`boot-dt.py` makes the tree patchable with **length-preserving byte edits**, so
each of these is a one-byte change to `boot.bin` (no rebuild, no CI, no
recompression) followed by a reboot. Keep the known-good image safe and always
write to a copy first.

The whole matrix is **already generated** in
`/home/sdolbec/dp-tunnel-artifacts/boot-variants/` (`config-A..D.bin` +
`MANIFEST.txt`), so each config is a single `cp` + reboot:

```bash
cd /home/sdolbec/wt-dockvideo
D=/home/sdolbec/dp-tunnel-artifacts/boot-variants
sudo cp $D/config-A.bin /boot/m1n1/boot.bin    # then reboot
python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin   # confirm
```

Regenerate them from the current image at any time (idempotent; `config-A.bin`
comes out byte-identical when the live tree is the installed state):

```bash
python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin --variants $D
```

The individual edits are still available if you want one-off changes:

```bash
sudo cp -n /boot/m1n1/boot.bin /boot/m1n1/boot.bin.$(date +%Y%m%d-%H%M%S)   # once
cd /home/sdolbec/wt-dockvideo
sudo python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin \
     --ablate-dp-tunnel --out /tmp/boot.bin.new      # 1 byte differs
sudo cp /tmp/boot.bin.new /boot/m1n1/boot.bin
python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin   # confirm
```

| config | `--mux-arg` | `apple,dp-tunnel` | what it isolates |
|---|---|---|---|
| **A — as installed** | 1 | present | experiments 1+2 together (the thing to try first) |
| **B** | 1 | ablated | experiment 2's DCP change alone: does leaving `atcphy` NULL matter? |
| **C** | 0 | present | experiment 1's routing alone (crossbar back to `dpphy`) |
| **D — baseline** | 0 | ablated | the tree as it was before any of this, with `allow_dp_tunnel=1`. **Never measured.** If D behaves like A, the crossbar route is not in the tunnelled path at all |

Restore A with `--restore-dp-tunnel --mux-arg 1`; restore the pristine tree from
`/boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455`.

Because the tree is shared by every GRUB entry, an ablation also applies to the
working `fairydust-usb4` kernel. That is harmless (it only changes which crossbar
input `dispext1` selects), but it means "boot the other entry to compare" does
**not** isolate the tree — only `boot-dt.py` does.

---

## 4. Hazards — read before touching cables

1. **Never unplug the dock while a DPRX read is in flight.** It deadlocks
   `apple_nhi_remove` against the `tps6598x` mutex and wedges the Type-C port
   (no hotplug, no USB, no charging) until a hard reboot — this is measured, see
   `DP-TUNNEL-RE.md` section 9. Make the port safe *first* by **arming** the
   bypass (write `1`; `0` restores the normal wait):
   `echo 1 | sudo tee /sys/module/thunderbolt/parameters/dprx_bypass`.
   With the bypass armed the read returns instantly, which is exactly why arming
   it *before* attaching the dock is the first step of section 1.
2. **Do not suspend with the USB4 dock attached.** The next boot after the
   experiment hung at `PM: suspend entry (s2idle)` and needed a power-cycle.
3. **The entry still carries `thunderbolt.dprx_timeout=3600000`.** With the
   bypass armed it is irrelevant; without it, a bounded-but-short value (a few
   seconds) is better than an hour, because an hour is an hour-long window for
   hazard 1. Editing it needs the ESP: mount-free edit of
   `/boot/grub/custom.cfg`, then `sudo update-grub` is *not* needed (`custom.cfg`
   is read directly).
4. Keep the monitor **on** and on the right input. A sleeping monitor can fail to
   answer DPCD, which is indistinguishable in the log from a broken host path.

---

## 5. Evidence to keep for the macOS-trace comparison

The macOS m1n1-hypervisor trace (second computer, `MACOS-TRACE-RUNBOOK.md`) is
what will explain the DCP's tunnelled-DPTX protocol. To make it comparable, save
per run:

- `~/dptunnel-logs/test-exp2-*.txt` (the collector's full output)
- `~/dptunnel-logs/exp2-live-*.txt` (the raw bring-up, unedited)
- the result of `python3 …/boot-dt.py --in /boot/m1n1/boot.bin`
- which config (A/B/C/D) was booted, and the monitor's physical port
- if anything came up: `cat /sys/class/drm/card2/card2-DP-1/{status,modes}`

Note `/tmp` is tmpfs here — everything must be written under `/home`.

---

## 6. Rollback

```bash
# tree back to pre-experiment, byte-for-byte:
sudo cp /boot/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-20261015-140455 /boot/m1n1/boot.bin
# or, without root-only sources, the zero-write path:
sudo python3 …/boot-dt.py --in /boot/m1n1/boot.bin --mux-arg 0 --ablate-dp-tunnel \
     --out /tmp/boot.bin.new && sudo cp /tmp/boot.bin.new /boot/m1n1/boot.bin
# then boot the normal 'elementary OS (M-series, fairydust-usb4)' entry.
```

The experimental entry and its kernel/initramfs can stay installed; they are not
the default and cost nothing while unused.

---

## 7. What this run should settle (and what is already settled)

The run's purpose is the one question at the top. In priority order:

1. **Does a real, powered sink on the dock's HDMI answer DPCD at all** — i.e.
   does `card2-DP-1` go `connected` with modes, unlike the DP→HDMI adapter in
   experiment 1? This is the frontier question.
2. If it answers: once the tunnel is up, does the DCP drive it by itself, or only
   after `force_link`? That decides whether experiment 3 needs a trigger or only
   a mode set.
3. Does `dprx_bypass=1` reach `activation complete` with the storm stopped
   (`DPRX bypass enabled, pretending DPRX completed`)? This only proves the
   fabric — it cannot produce video (`DP-TUNNEL-RE.md` §6.1) — so it is
   diagnostic, not a goal.

**Already settled — do not re-derive:** the crossbar route is correct and the host
tunnel forms (§5); `dprx_bypass` cannot fill `DP_LOCAL_CAP`; the DCP firmware
owns sink detection (call 20). Not worth a reboot unless you have spare time: the
`1:13`/`1:14` ↔ physical-port mapping, the `0:5` ↔ `dpin0` mapping, and the
`dprx_timeout` bookkeeping.

---

## 8. Do NOT spend tomorrow on this

Lessons from 2026-10-15, a full day that produced no picture:

1. **Do not write more driver/DT "triggers" to force video.** The DCP firmware —
   not the Linux driver — detects the sink on the tunnelled path, and it reports
   none (`acking unhandled call 20` = `INACTIVE_SINK_DETECTED`). `dprx_bypass`
   cannot fill `DP_LOCAL_CAP`, so forcing activation cannot yield a picture
   (`DP-TUNNEL-RE.md` §6.1). A silent sink *is* an answer.
2. **Do not build a new kernel.** Experiment 2 is installed and running; a CI
   round trip + install + reboot is about an hour for no new information.
3. **Do not run the whole A/B/C/D ablation** unless the sink answered and you
   still have time (section 3) — four reboots, and the host side is already
   proven.
4. **Do not unplug the dock while a DPRX read can be in flight** — i.e. unless
   the bypass is armed (section 4). It wedges the port until a hard reboot; arm
   the bypass (write `1`) first.
5. **Do not chase the adapter/port mappings or the `dprx_timeout` bookkeeping**
   before the sink question is answered.

When the sink stays silent, the correct pivot is the macOS trace
([`MACOS-TRACE-RUNBOOK.md`](MACOS-TRACE-RUNBOOK.md)) — not more time at the dock.
