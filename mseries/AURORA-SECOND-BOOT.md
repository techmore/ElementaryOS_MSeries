# Aurora SEP kernel: second-boot plan (written 2026-10-17)

Why: the first boot of `7.1.12-2-20261015.19-sep-ARCH` brought the Secure
Enclave up, then the machine hung ~34 s in with no panic logged. See
[aurora-touchid-state.md](aurora-touchid-state.md) and the top entry of
[OS9-HANDOFF.md](OS9-HANDOFF.md). Nothing here has been run on a boot yet.

## Already prepared (this session)

- journald drop-in `/etc/systemd/journald.conf.d/zz-aurora-freeze-hunt.conf`
  (`SyncIntervalSec=1s`, `RateLimitIntervalSec=0`) so the last seconds before a
  freeze reach disk. Installed and journald restarted; harmless on any kernel.
  **Remove after the test:** `sudo rm /etc/systemd/journald.conf.d/zz-aurora-freeze-hunt.conf && sudo systemctl restart systemd-journald`
- No GRUB or m1n1 change was made. Fallback is any other GRUB entry (default
  `elementary-mseries` is unchanged).

## Observations to act on before booting

1. The GRUB entry `elementary-aurora-sep` (in `/boot/grub/custom.cfg`) still
   carries the dptunnel experiment flags
   `thunderbolt.allow_dp_tunnel=1 thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=15000`.
   They belong to the fairydust kernels; on Aurora they are probably ignored but
   are an uncontrolled variable. For a clean test, use a copy of the entry
   without them, and without `quiet` (loglevel 3 hides kernel warnings).
2. Boot with the dock detached (earlier community j314s reports of flaky boots).
3. Journal ends abruptly on a hard reset, so the real uptime may exceed 34 s.

## Test sequence (needs owner OK for the boot)

1. Boot the Aurora entry once, dock detached, nothing launched by hand.
2. Note wall-clock time of the freeze, and whether the screen froze, went
   black, or the machine reset by itself.
3. After recovering on any kernel: `journalctl -b -1 -o short-monotonic | tail -60`
   and check `/sys/fs/pstore` (needs root).
4. Only if it stays up for several minutes: `ls /dev/sep-bio`, `fprintd-list $USER`,
   then `sudo aurora-touchid-setup`.

## Suspects

SEP background activity after ready; the ported `spi@39b108000` fingerprint
node; DCP/display ("DCP took too long to respond to LAS stats"); an unrelated
fault in this kernel build. To separate them, an optional bisect is booting with
the pre-fingerprint DTB (`/boot/m1n1/boot.bin.pre-fingerprint-20261017-103254`);
that changes the bootloader payload, so it needs explicit owner approval.

## Update 2026-10-17: clean GRUB entry added

Added `elementary-aurora-sep-clean` ("CLEAN freeze test, no dock flags") to
`/boot/grub/custom.cfg`: same kernel and initramfs, no `thunderbolt.*` flags, no
`quiet`/`splash`, `loglevel=7`. The original `elementary-aurora-sep` entry and the
default are untouched; the pre-edit file is saved as
`/boot/grub/custom.cfg.pre-aurora-clean-*`. Nothing was armed (`grub-reboot` not
run). To boot it once: pick it in the GRUB menu, or `sudo grub-reboot elementary-aurora-sep-clean`
(owner decision). Revert: restore the saved `custom.cfg`.

## Result of the clean-entry boots — 2026-10-17 22:03–22:05

Booted `elementary-aurora-sep-clean` (loglevel=7, no thunderbolt flags, journald
sync 1 s). Owner reports the machine keeps crashing.

- Boot A (22:03:21, journal ends 22:03:44, last entry 33.0 s): ended with no
  panic/oops/shutdown in the log, again with the desktop up. Same ~33 s as the
  first freeze (~34 s), which points to something deterministic at that point of
  startup, not random. Last events: mseries-dark-mode.service (32.97 s), ibus
  im-config, Claude Desktop GTK assertion.
- Boot B (22:04:50): still alive at 46 s+ when checked; `/dev/sep-bio` exists
  (root-only, char 10:261); `fprintd` inactive (on demand). SEP firmware accepted
  as before. Journal errors only: `tas2764 3-003c: Failed to parse devicetree`
  (speaker amp on this DTB), brcmf p2p -52, bluetooth flag warnings.
- pstore empty; PMU reports "1 boot error(s) and 0 panic(s)" after the reset.
- Nothing from SEP/DCP/SPI-fingerprint precedes either stop.

Open: whether Boot B froze later, whether a hardware watchdog/SMC reset (not a
kernel panic) is the cause, and the tas2764 devicetree warning (new on this
kernel/DTB; stock kernel path unchecked). Stock `7.1.13-3-2-ARCH` is stable and
remains the default. No further Aurora boots until the owner decides.

## Boot B outcome — 2026-10-17 22:04:50–22:06:23, and the dock

Boot B survived past 33 s and ran 93 s. At 22:05:52 (owner touched the dock/USB-C)
the kernel removed both xHCI controllers and the Apple ATC PHY logged
`Pipehandler lock not acked` / `Failed to lock pipehandler`; the journal ends
about 31 s later with no panic. So the Aurora kernel mishandles a USB-C/dock
event, and that is a strong candidate for at least this crash. Boot A and the
first boot (~33–34 s) had no dock event in the log, so they remain unexplained.
The Aurora kernel has none of the fairydust USB4 work, so the dock (hub, mouse,
Ethernet) does not work there. Dock and Touch ID cannot share a kernel yet.

Touch ID app: installed as "Touch ID" (`~/.local/bin/mseries-touchid-settings`,
desktop entry in `~/.local/share/applications`); source in `mseries/aurora-touchid/`.
Enrollment only works on the Aurora kernel, dock unplugged.

## Bisect step 1 — is it the SEP driver or the Aurora kernel? (2026-10-18)

Owner: the Aurora kernel froze on every boot. Fact: the same patched m1n1 DTB
(SEP enabled + alias + sensor node) boots the stock `7.1.13-3-2-ARCH` kernel
stably (no apple_sep driver there, so the node sits inert). New GRUB entry
`elementary-aurora-nosep` = Aurora kernel with `module_blacklist=apple_sep,apple-sep`.
If it stays up for 10+ minutes, the SEP driver (or its SEP firmware traffic) is
the cause; if it still freezes, it is the Aurora kernel build or the dock/USB-C path
(unplug everything). Nothing armed. Backup: `/boot/grub/custom.cfg.pre-aurora-nosep-*`.

## More Aurora boots, read-only analysis — 2026-10-18 03:39–03:41

Three further Aurora boots, all via the ORIGINAL `elementary-aurora-sep` entry
(loglevel=3 quiet + thunderbolt dptunnel flags; the clean and nosep entries were
not used):

| boot | wall time | end |
|---|---|---|
| 03:39:47 | 7 s | clean systemd shutdown (owner rebooted) |
| 03:40:22 | 15 s | journal stops at 21 s monotonic, no panic |
| 03:41:31 | 20 s | journal stops at 27 s monotonic, no panic |

Findings: no SEP/DCP/GPU/ATC error precedes any stop; the Asahi GPU driver loads
identically (37 lines) on Aurora and stock; every stop is during desktop
startup (gala/dock/pipewire). PMU reports 1 boot error / 0 panics on every boot
including stock, so that line is not discriminating. pstore is empty. Because
the owner reboots quickly, some stops may be manual power-offs rather than
hangs — unknown until we know what the screen showed.

Still the next test: `elementary-aurora-nosep` (SEP driver blocked), dock and
all USB-C unplugged, left alone for 10 minutes. Questions for the owner: when
it "freezes" is the screen frozen or black, and did you hold the power button?

## Owner's description of the failure — 2026-10-18

"The mouse just stopped; waited about a minute and it shut off by itself, every
time, within about a minute of boot." So this is a **whole-system hang** (input
dead, journal silent, no panic) followed by a **hardware power-off/reset about
a minute later** — consistent with the SMC/PMU watchdog firing because the kernel
stopped responding, not with a userspace crash. This is why no log line precedes
the stop. The earlier Aurora boot at 10:50 on 2026-10-17 also ends abruptly ~2 min
in (no shutdown messages), so the first Aurora-with-SEP boot of the day likely had
the same fault. The patched DTB (incl. `spi@39b108000`/`fingerprint@0`) is present
in the running device tree. The stock kernel, which never touches those nodes,
is stable on the same DTB.

Candidates, in order of how cheaply they separate: (1) `elementary-aurora-nosep`
(SEP driver blocked) — tests the SEP driver; (2) boot with
`boot.bin.pre-fingerprint-20261017-103254` — tests the ported sensor node, whose
clock/pinctrl phandles were flagged as unresolved when it was ported (a wrong
reference on a live block can hang the machine, as the 2026-10-17 note warned).
Test 1 needs no bootloader-payload change; test 2 does (owner OK required).

Owner confirmed 2026-10-18: the hang happens with the dock NOT attached, so the
dock/USB-C event is not the cause (it was at most a coincidence in one boot).
Armed one-shot `elementary-aurora-nosep` (SEP driver blocked) for the next boot.

## RESULT: `elementary-aurora-nosep` is stable — 2026-10-18 04:03

Aurora kernel with `module_blacklist=apple_sep,apple-sep`, dock out: no hang, up
5+ minutes (previous Aurora boots died within 15–60 s), desktop normal. So the
hang needs the **SEP driver (`apple_sep`) loading**; the Aurora kernel itself and
the patched DTB (including the sensor node) are fine with the driver blocked.
`apple-sep.path`/`apple-sep.service` load it automatically at boot (modprobe
~14 s after start), so no "probe" by us is needed to trigger it. In every
hanging boot the SEP had finished boot-up and registered its hwrng 5–26 s before
the journal ended; the kernel's hw_random fill thread reading from the SEP RNG is a
prime suspect (untested). Next: report to omacom/linux-aurora with these logs;
possible cheap tests — load `apple_sep` by hand on this entry after a stable
period (expect a hang; save work first), or find a parameter that disables its
hwrng registration. Until fixed: do not enable `apple-sep.path` on any default entry.

## Upstream check: omacom/linux-aurora `.20` vs our `.19` — 2026-10-18

Release `aurora-2026.10.17.20` (2026-10-17) exists; we run `.19`. Findings:

- **Dock claim, scoped:** `.20` notes report a CalDigit TS4 Thunderbolt dock
  (PCIe devices, Ethernet, external DisplayPort) working — on an **M1 Air** lab
  package. M3 Pro tested with an external DisplayPort display. **"Not tested on
  hardware: ... the M1 Pro and Max, ... Touch ID."** Our j314s (M1 Pro) + Dell
  WD22TB4 is untested upstream; `.20` also has an HPD-relink and USB-C retrain
  change for M1-M3 display/USB-C. Worth trying, not yet evidence for us.
- **Touch ID in `.20`:** sensor CRC/re-read/stale-frame drain, serialized sensor
  exchanges, 6 s wait for capture stop, "an empty host-state file is set up
  again". `hwrng.rs` and `hwrng_shim.c` are byte-identical to `.19` (quality 1024,
  so the hw_random core uses it). `sep.rs`, `sbio.rs`, `sensor.rs`, `mailbox.c`,
  `rtkit.c` changed. Nothing in the notes mentions a whole-system hang after
  attach. SEP bindings doc now says on T8140 the SEP stops servicing its mailbox
  for good if a dependent power state is switched off (T8140 only).
- **Known issue to cite:** omacom/linux-aurora issue #42, "M1 Pro SEP: retain
  unresolved attach and post-resume session failures" — J314S "transient attach
  failures", priority P2, investigation. Our hang is a harder failure than that.
  No open issue matches a freeze/power-off after attach on j314s.
- **Next:** install `.20` (their installer `install-aurora-sep.sh`; it replaces
  our manual Aurora install, so do it deliberately), boot it with the dock out,
  and if it still hangs file a new issue citing #42 with the logs in this file.
  Caution: `.20` is a large rebase (new memory-management paths for every
  process), so test it on its own GRUB entry, not as the default.

## Aurora `.20` installed side by side — 2026-10-18 (not yet booted)

Downloaded `linux-aurora-7.1.12.aurora2-20261017.20-aarch64.pkg.tar.zst` from the
omacom/linux-aurora release (SHA256 verified against the release `SHA256SUMS`;
extracted into a scratch dir and inspected first). Installed by hand, mirroring
the `.19` layout (the upstream `install-aurora-sep.sh` was NOT run):

- modules: `/usr/lib/modules/7.1.12-2-20261017.20-sep-ARCH/`
- kernel: `/boot/vmlinuz-aurora-sep-20261017.20`
- initramfs: `/boot/initrd.img-7.1.12-2-20261017.20-sep-ARCH` — rebuilt from the
  `.19` initramfs layout (same early part, gzip main, same module list, `.20`
  modules + `drm_dma_helper.ko`; `apple-tunable` and `typec` are built in now).
  A first attempt with Debian `update-initramfs` was discarded: it does not
  understand the Arch `cryptdevice=` boot option.
- GRUB (`/boot/grub/custom.cfg`, backup `custom.cfg.pre-aurora20-*`):
  `elementary-aurora20` (SEP enabled, the real test) and
  `elementary-aurora20-nosep` (driver blocked). Nothing armed; default unchanged.
- `/boot` is 96% full (22 MB free). Old fairydust initramfs files are the
  obvious candidates to prune; not touched.
- Test: dock out, `sudo grub-reboot elementary-aurora20`, leave it 10 minutes. If
  it boots but hangs, boot `-nosep` to confirm and file an upstream issue citing
  #42. If it does not boot at all, pick any other GRUB entry; nothing else changed.

## Community call for Aurora testers (owner pasted 2026-10-18) — NOT run

A post by Chris Kearney (@SiliconForested) asks Omarchy Mac users to test a custom
kernel with Thunderbolt support, SEP (Touch ID) and AVD improvements, and to have
an AI agent run the installer and report findings, with fixes to flow upstream
to the Aurora Linux project by pull request (agent commit hashes preserved).
It asks testers to try a Thunderbolt dock, sleep/resume USB and display, and to
report anything that fails. Back up first; there is a chance of breaking the install.

What we checked (2026-10-18):
- The post's installer URL is
  `iconidentify/aurora-linux` release `sep-7.1.12.aurora2-11.2`
  (2026-09-29, "M2 Max (t6021) test build"). That repository is **archived**
  ("Frozen at Aurora 2026.10.10.12"; development moved to `omacom/linux-aurora`).
  So the link is an old test build, older than our `.19` and the current `.20`.
- We did **not** run the `curl | bash` installer (it replaces the kernel and
  boot setup); use the current `omacom/linux-aurora` release (`.20`) instead,
  installed side by side as described above.
- Our test is exactly what the post asks for: M1 Pro (j314s) + Dell WD22TB4 dock,
  Touch ID, and resume. Report to omacom/linux-aurora (issue #42 is the related
  M1 Pro SEP ticket) with the logs in this file, including the hard hang with the
  `apple_sep` driver loaded on `.19`.

## The community installer's test plan, read (not run) — 2026-10-18

Fetched `install-aurora-sep.sh` from the post's URL into a scratch directory and
read it (sha256 `7956337789360242d06e0190e131e968b3cbbc9c10b23656a7e00da5698347ec`,
old 11.2 build). It is an Omarchy/pacman installer (replaces `linux-asahi`, runs
mkinitcpio/update-m1n1, adds a fallback GRUB entry); ours is elementary with a
manual layout, so we mirror it by hand. Its `--agent-prompt` is a good test plan:

1. **Identify the machine:** `/proc/device-tree/compatible`,
   `chosen/asahi,os-fw-version` and `asahi,system-fw-version` (the sepOS version is
   "the single most useful line"), `uname -r`, package versions.
2. **m1n1 guard (M2+ only):** expect "SEP: sepOS already booted by iBoot"; on M1
   (our j314s) the enclave is cold and m1n1 talks to it normally, no guard line.
3. **Driver attach:** `modprobe apple_sep xart_writes=0 provision_keybag=0`;
   pass = "attach: N endpoints advertised" with N >= 7 and `/dev/sep-bio`.
4. If attach fails: A2I/I2A mailbox control registers (`devmem 0x396408110/114`
   on t600x).
5. Touch ID: `aurora-touchid-setup`, `fprintd-verify`, then sudo, polkit and lock
   screen separately.
6. Thunderbolt/DP: devices in `/sys/bus/thunderbolt/devices`, boot/hot-unplug/
   replug on **both** ports, PCIe behind the dock, across suspend.
7. Video decode; 8. final suspend/resume.
Safety rules: confirm the owner can **DFU-restore** the Mac first (it touches the
Secure Enclave); **do not pass `xart_writes=1` or `provision_keybag=1`** or run
enrol/delete loops without written owner approval; never paste key material,
serials or `mesa_calibration.bin`. Report format: one comment on the SEP PR
(omacom/linux-aurora PR #7) with Machine / Firmware / Build / m1n1 guard /
Thunderbolt headers, What worked / What did not / Logs; quote logs exactly, say what
was not tested, name the dock and display mode.

**Relevance to our hang:** the plan loads the driver by hand with
`xart_writes=0 provision_keybag=0`, whereas our boots auto-load it through
`apple-sep.service` with defaults (the driver logged an xART "writes ENABLE" line
on every Aurora boot). The default path may do more (xART/anti-replay writes,
keybag work) than the plan's cautious path. Cheap next test: on the `.20` nosep
entry, `sudo modprobe apple_sep xart_writes=0 provision_keybag=0` by hand and see
whether the hang disappears. Save work first.

## /boot cleanup — 2026-10-18

`/boot` was 96% full (22 MB free). Removed only `boot.bin.pre-sep-alias-20261017-102233`
(an intermediate m1n1 state, superseded) and the 4 KB `._boot.bin` AppleDouble
file. Every kernel/initramfs left is referenced by a GRUB entry, so nothing else was
touched. Bigger savings need a decision: the three fairydust dptunnel test initramfs
(`-dpin-clock`, `-dpin-controlled`, `-dptunnel-vrr`, ~29 MB each) belong to the
DeepSeek kernel work; the `.19` Aurora kernel+initramfs (~59 MB) can go once `.20` is
judged. Kept deliberately: `boot.bin.pre-sep` (the fallback-safe payload),
`pre-fingerprint` (the bisect fallback), `pre-e4`.

## omacom/linux-aurora `aurora-wip` and the Thunderbolt branches — 2026-10-18

- `aurora-wip` (tip `4ec597a7`, 2026-09-05, "Merge AsahiLinux fairydust into
  aurora-wip") is DjDeveloperr's integration branch. It is **behind** the `.20`
  release by 2244 commits (0 ahead): `.20` is built from the merge of aurora-wip
  with the review fixes (PR #136, which superseded #131), so nothing in the branch is
  missing from `.20`. Its last commits are dp-altmode DTS "hacks" for t8103/t8112/
  t60xx (including j314/j316) plus `usb: typec: tipd: HACK: Use drm oob hotplug event`
  and `Track data_status changes for CD321x` — DisplayPort alt-mode plumbing.
- Other related branches: `tb` (ProMotion variable refresh, 2026-09-12),
  `usb4-base` (thunderbolt/net interrupt throttling), `carry/pr92-tb-s2idle`
  (2026-10-15, "thunderbolt: apple: ... contain resume recovery"),
  `fix/m3pro-hdmi-thunderbolt`, `review/j613-external-dp`.
- Both `.19` and `.20` already carry the j314/j316 USB4 device-tree work (ACIO and NHI
  nodes, tunnel routing, m1n1 v1.6.1 USB4 aliases, `dcpext0` lent to the Type-C
  ports). Our running boot device tree already has the `usb4-N-acio`/`usb4-N-nhi`
  aliases and three `cio@` nodes, so the community plan's "missing alias" failure
  (step 6a) is NOT our problem. Yet on our `.19` boot `/sys/bus/thunderbolt/devices`
  was empty and a dock event removed the xHCI controllers with
  `phy-apple-atc: Failed to lock pipehandler`. The thunderbolt/ATC path therefore
  needs its own `.20` test (on the nosep entry, to keep the SEP hang out of it).
- Community note: their m1n1 for this is `m1n1-aurora-1.6.1.aurora17-5` (in the
  `.20` release; not installed here — our boot payload is the DeepSeek-managed
  `boot.bin`; replacing it is a bootloader change that needs the owner's explicit OK).

## .19 deleted; repo .20 lane finished on the machine — 2026-10-18

Deleted `.19` (kernel + initramfs from `/boot`, three GRUB entries; module dir stays while
booted on it). Found that the repo already has the `.20` port (`mseries/aurora/`, PR #78); ran
its `stage-boot.py` to stage the matched m1n1-aurora + J314S DTB `boot.bin` candidate in
`~/aurora20-boot-candidate/` (not deployed). `/boot` is now 83% (89 MB free). Details and the
recommended test order are in [aurora/README.md](aurora/README.md#status-on-the-owners-m1-pro--2026-10-18-claude-code).
