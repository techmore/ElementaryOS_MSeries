# Dock code review and reproducible validation

Reviewed 2026-10-17 against main after PR #76. This branch retains experiments E1/E3/E4;
it does not establish that WD22TB4 HDMI works. The last retained hardware record is
[E4 armed](evidence/2026-10-17-e4-armed.md), with no recorded E4 boot outcome.
[PRIMARY-GOAL.md](PRIMARY-GOAL.md) defines the evidence gates and
[STATE-OF-PLAY.md](STATE-OF-PLAY.md) retains the hardware history.

## Defects fixed

- The shell collector hardcoded dcpext1, assumed every DT property existed, looked for DRM
  connectors under a nested layout, and could infer a working tunnel from an unrelated external
  connector or activation log. It now delegates to `inspect-dock.py`, resolving the NHI source
  phandle and examining the mapped DCP's latest completion. Positive link evidence needs a
  nonzero rate, valid lane count and successful completion. Logs remain historical evidence;
  connector state/EDID must still be correlated with the dock, and picture verification is manual.
- Missing/unreadable state stays unknown. External connectors use the normal flat sysfs paths;
  eDP is excluded. EDID checks include declared extension count and all block checksums.
  Collection issues no sudo calls, sysfs writes, force-link commands or cable manipulation.
- The controlled-test module collector now checks each module's frozen SHA-256 before comparing
  its build ID with the loaded module. Truncated ELF notes fail closed; boolean parameter reporting
  accepts both Y/N and 1/0. Its checks also record whether tunnelling is enabled.
- Archive path normalization now collapses equivalent names before duplicate checks, rejects NULs,
  and refuses to add a file below a symlink or non-directory parent. The staging regression now uses
  a scratch GRUB environment instead of reading the host's `/boot/grub/grubenv`.
- Merged current main, preserving power code and dock history. Status pages distinguish the last
  captured E4 state from a current read and mark older deployment plans as historical.

## Run the software checks

```bash
for f in mseries/fairydust/usb4/test-*.py; do python3 "$f"; done
python3 mseries/fairydust/usb4/tools/test-staging-tools.py
bash -n mseries/fairydust/usb4/test-dp-tunnel.sh
```

These cover 36 offline unittest cases plus three staging test groups. They include 12 new route,
missing-data, stale-result, frozen-module, ELF-note and archive-path regressions.

For reproducible source checks, download the exact public Fairydust archive used by
`mseries/fairydust/debian/build.sh` and pass a fresh scratch directory:

```bash
curl -fL --retry 2 https://codeload.github.com/AsahiLinux/linux/tar.gz/ce9f2eba72c061a50b2d790450e90af3439d8c24 -o /tmp/fairydust-dock.tar.gz
python3 mseries/fairydust/usb4/tools/validate-dock-patches.py --archive /tmp/fairydust-dock.tar.gz --output /tmp/dock-review-new
```

Requirements: Python 3.11+, git, a C compiler, bison and flex. `CC`, `BISON`, `FLEX` can select
executables; on macOS a current bison may need its explicit package-manager path. No root is needed.
The validator checks the existing archive SHA-256, extracts selected regular source files, applies
0001–0015 in sequence and builds the pinned in-tree dtc. It changes no floating-point cells to
accommodate a stock compiler. It runs the actual production helper/function fixtures: 11 handshake,
11 clock, 7 EPIC, 28 bridge, 11 managed-PHY and 8 HPD-policy groups, including the undefined-behavior sanitizer.
The HPD harness compiles the actual E1 worker and checks that physical errors still fail while tunnel errors remain nonfatal.
It compiles E3/E4 and a non-target control board, verifies source-controller selection and E4's HDMI
endpoint removal, and compiles the Touch ID delta with unchanged dock routing. The control board
must be byte-identical before/after E4. Output includes a command log and SHA-256 evidence report.

The same commands run in Linux PR CI. The retained
[local validation receipt](evidence/2026-10-17-offline-code-audit.json) records the source pin,
all patch hashes and DT hashes. Expected inherited DT warnings are retained in the scratch command
log. This is **not** a complete kernel/module build, lock/race proof, hardware boot, EDID qualification,
video/suspend test, or a new driver implementation. The original experimental patches are retained;
no new firmware command or reverse-engineering hypothesis was introduced by this audit.

## Qualification and deployment boundaries

Normal Debian builds still apply only their existing explicitly selected patch set; this review does
not silently enable E1/E3/E4 in a production kernel. Validation creates scratch binaries and DTBs only.
E4 removes the built-in HDMI controller mapping and affects every boot entry if installed in global
`boot.bin`. The older fallback-preserving installer rejects E4's wider DT changes by design; do not
relax or bypass that check to install it.

The Aurora report on [j314s Thunderbolt-display resume](https://github.com/omacom/linux-aurora/issues/38#issuecomment-6117263883)
explicitly records zero tunnel up/down events and keeps the existing route allocated. It is useful
prior art, not WD22TB4 HDMI qualification. The [M2 Max dock report](https://github.com/omacom/linux-aurora/issues/132)
uses a different model/dock/adapter and reports its own limits.

Next hardware task: inspect the actual current payload and one-shot state, then review a controlled
boot separately. Record the mapped DCP and loaded module identities, link configuration, external
connector modes/EDID, and the owner's observed picture as separate results. No reboot, global boot
payload replacement, module reload, audio change or cable exercise was performed in this audit.
