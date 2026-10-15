# Tomorrow's runbook — dock video over USB4 DP tunnelling (2026-10-16)

Everything here is prepared offline. The dock and monitor are the only missing
pieces. Read section 0, then run section 1 top to bottom; the decision tree in
section 2 tells you what each outcome means, and section 3 is how to answer more
than one question per reboot without waiting for CI.

Background and the full reverse-engineering map: [`DP-TUNNEL-RE.md`](DP-TUNNEL-RE.md).
The measured hazard that cost us the last machine: `DP-TUNNEL-RE.md` section 9.

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
`0002-experimental-dp-tunnel.patch`, and on this branch that pin is still
experiment 1's (`b251b716…`), while experiment 2's patch lives on `re/usb4-exp2`
(pin `c962eff0…`). Sync *both* files from that branch, or just reinstall from the
stash above — the CI build is what produced the installed kernel either way.

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

```bash
cd /home/sdolbec/ElementaryOS_MSeries
python3 mseries/fairydust/usb4/boot-dt.py --in /boot/m1n1/boot.bin
```

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

Disarm before you touch the cable (see section 4).

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

**Two probes worth doing regardless of the outcome**

1. **Which dock DP OUT adapter is which physical port?** The log only ever says
   `1:13` / `1:14`. Attach the monitor to exactly one dock output at a time and
   note which adapter acks the hotplug (`acking hot plug event on 1:1x`). That
   mapping is free and removes a whole class of confusion tomorrow.
2. **Which host DP IN adapter is our dpin0?** We route the crossbar to `dpin0`
   and the CM independently picks `0:5`. The `0:5` <-> `dpin0` correspondence is
   inferred, not measured. `boot-dt.py --mux-arg 2` (dpin1) is the cheap test: if
   `0:6` then pairs and behaves the same, the mapping is "5=dpin0, 6=dpin1"; if
   the crossbar route stops mattering, then the crossbar is not in the path at
   all — a genuinely useful negative result.

---

## 3. One reboot, several answers: the ablation matrix

`boot-dt.py` makes the tree patchable with **length-preserving byte edits**, so
each of these is a one-byte change to `boot.bin` (no rebuild, no CI, no
recompression) followed by a reboot. Keep the known-good image safe and always
write to a copy first.

```bash
sudo cp -n /boot/m1n1/boot.bin /boot/m1n1/boot.bin.$(date +%Y%m%d-%H%M%S)   # once
cd /home/sdolbec/ElementaryOS_MSeries
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
   `DP-TUNNEL-RE.md` section 9. Disarm first:
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

## 7. Open questions this run should close

1. Does `dprx_bypass=1` actually get the tunnel to `activation complete`
   **without** the DPRX storm? (Expect `DPRX bypass enabled, pretending DPRX
   completed` per attempt.)
2. Once the tunnel is up, does the DCP drive it by itself, or does it need
   `force_link`? This is the single most important observation: it decides
   whether experiment 3 has to synthesise a trigger or only a mode set.
3. Sink side: does a real, powered sink on the dock's **HDMI** answer DPCD at
   all (`card2-DP-1` `connected`, EDID read), unlike the DP→HDMI adapter?
4. The `1:13`/`1:14` -> physical port mapping, and whether the CM's `0:5` really
   is our `dpin0`.
5. Bookkeeping: the `re/usb4-exp2` notes date the last storm to
   `dprx_timeout=-1`, while the boot-`-2` command line carried no `dprx_timeout`
   at all (module default). Worth settling so the operational rule is right.
