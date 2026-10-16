# MacBook Neo recorder preparation — 2026-10-16

The separate recorder has now been identified and accessed successfully.
It is a **MacBook Neo, Mac17,5, Apple A18 Pro, 8 GB RAM**, running
**macOS 26.6.2 (25G83)**, with approximately 402 GiB free at inspection.
Its OS version is the **recorder** OS, not the version we will boot under
m1n1 on the M1 Pro. The guest compatibility requirements apply to the target.

## Access and power

- SSH login was successful using the owner-provided account.
- At the owner's explicit request, the existing Linux public SSH key was
  installed with `ssh-copy-id`; a separate `BatchMode=yes` login succeeded.
- Passwords, usernames, machine serial/hostname, IP addresses, SSH keys and
  raw registry data are not included in this public handoff.
- A tracked `caffeinate -dimsu` process runs on the Neo. `pmset -g assertions`
  confirmed idle-system, system-sleep and display-sleep prevention. It survives
  closing the SSH session. Keep the lid open and use reliable power.
- Stop only our tracked process when capture is finished:

```bash
sh "$HOME/Documents/DockVideoRecorder/STOP-KEEP-AWAKE.sh"
```

- A separate `systemd-inhibit --what=sleep --mode=block` assertion is active
  on the M1 Pro Linux session. Its PID/log are recorded privately in this
  chat's `work/neo-recorder/` directory. This complements the existing docked
  lid handler; it is not a permanent power configuration change.

## Staged files and verified checks

Everything is under `~/Documents/DockVideoRecorder` on the Neo:

| Location | Contents / status |
|---|---|
| `runtime/python/` | Project-local CPython 3.13.16 for Darwin ARM64; version executed successfully |
| `deps/` | Pinned upstream requirements: asn1 3.3.0, construct 2.10.70, enum-compat 0.0.3, pyserial 3.5 |
| `m1n1/` | Source from `c6a89b908ac4bf1f7b495f20531f3ea029148adb`, including licenses |
| `m1n1/build/` | Freshly built matching `m1n1.bin` and `m1n1.macho`, staged only, not booted or installed |
| `wd22tb4-cutover-kit/` | Reviewed collector/hooks/checklists from repository commit `5163f9a`; archive manifest verified |
| `tools-current/` | Updated importer and checked capture hooks; preserves the original archive's verified manifest |
| `env.sh` | Recorder-only Python/dependency/toolchain environment; source before using the tools |
| `downloads/` | Original runtime, source, binary and toolchain files, kept for provenance |
| `validation/01-recorder-selftest/` | Private native macOS collector self-test on the Neo, **not M1 Pro dock evidence** |
| `keepawake.pid`, `keepawake.log` | Our tracked recorder sleep assertion |
| `STOP-KEEP-AWAKE.sh` | Stops our assertion without touching other caffeinate processes |

The system's `/usr/bin/python3` and Git/compiler commands were developer-tool
stubs; no active Command Line Tools directory was present. We used a private
runtime instead of changing system Python or installing Xcode/Homebrew.

Verified on the Neo:

1. Python version and m1n1 hypervisor import; construct/serial imports.
2. `run_guest.py --help` completes with the staged runtime/dependencies.
3. All 12 preparation tests pass on the actual Darwin ARM64 recorder.
4. The native collector produces valid IODeviceTree, IOService and display /
   USB profiler plists, root/APFS inventories and filtered kernel log output.
   The Preboot kernelcache search returns a permission error without sudo,
   which is preserved in its stderr/status file. The collector exits 1 for
   that failure while retaining successful files, as designed.
5. The Neo's real IODeviceTree export is a root dictionary rather than a
   one-item list. The importer was corrected to accept both shapes, blank
   ADT names with registry-name fallback and anonymous non-ADT leaves,
   retaining rejection of ambiguous roots. Its fixtures cover these cases.
   It then parsed the real Neo archive successfully (2 selected nodes,
   8 context nodes). These are Neo nodes, not the M1 Pro's missing DP-IN data.

The Neo self-test does not confirm the target's DP-IN metadata or HDMI video.
Do not upload its raw `PRIVATE` registry/log files as dock evidence.

## Runtime provenance

Private CPython comes from the maintainers' portable distribution:

- [Astral python-build-standalone release 20261013](https://github.com/astral-sh/python-build-standalone/releases/tag/20261013).
- File: `cpython-3.13.16+20261013-aarch64-apple-darwin-install_only.tar.gz`.
- SHA-256 verified before extracting:
  `ca0e6a70fb75a0984751bd75493e3de77680aef7fbd0fea9b903c299537b3423`.
- [Distribution format documentation](https://github.com/astral-sh/python-build-standalone/blob/main/docs/distributions.rst).

Matching m1n1 binaries were built in an isolated source checkout on Linux,
with no boot/kernel changes, using:

```bash
git rev-parse HEAD   # c6a89b908ac4bf1f7b495f20531f3ea029148adb
make -j2 build/m1n1.bin build/m1n1.macho LOGO=
```

Hashes of the prepared artifacts:

| File | SHA-256 |
|---|---|
| `m1n1.bin` | `b624f862ea6d17b4a9ea991254f4dc1a08a9de5621f21c81e50d89cdbcfb5f2a` |
| `m1n1.macho` | `a5d7f9684fce8224f7efc0c1e6ce756f128309d7b17da75a452ef9ad2b11d5c6` |
| Source archive produced with `git archive`, prefix `m1n1/` | `4dd5be333f303fac0af89cdd8e7d83ed27077f1a15ac8cf3364c5ea5518fe66e` |

The current source also needs ASN.1 dependencies; the older local extracted
tree used only construct/pyserial. `m1n1-trace-deps.sh` now includes all four
pinned pure-Python requirements and validates wheel hashes from PyPI metadata.
Do not equate these source revisions or reuse their binaries interchangeably.

## Compiler completion and remaining capture gates

m1n1's host Python client assembles small target-side instruction stubs.
Python imports alone are insufficient: the Neo also needs a working AArch64
assembler, ELF linker, objcopy and nm. The official portable LLVM bundle is
being prepared under this project folder, without a system installation:

- [LLVM 23.1.3 release](https://github.com/llvm/llvm-project/releases/tag/llvmorg-23.1.3).
- File: `LLVM-23.1.3-macOS-ARM64.tar.xz` (about 1.57 GB download).
- Expected SHA-256:
  `3dcfd88aec10be204a24037bcb0dc0ad777882e9dbe8ac60e2639060d8a794b1`.
- Before calling the toolchain ready, verify that hash, extract the bundle,
  select its `bin/` directory in `env.sh`, and test `ARMAsm("nop; ret")`.

After compiler completion, the still-required items are:

1. A direct USB data cable from the Neo to a **free** M1 Pro Thunderbolt port.
   Leave the WD22TB4 and its HDMI monitor on their current target connections.
   The recorder does not need to own the dock or have Thunderbolt itself.
2. The M1 Pro's native macOS baseline and exact macOS build/kernelcache.
3. A validated, owner-approved guest boot route and supported target version.
4. Confirmed DP-IN/DCP/DART mapping and dependency trace ranges from its ADT.
5. Proxy serial-device enumeration and a successful handshake.

No target proxy, guest, security downgrade or boot modification has been
executed. The recorder's SSH success is not a successful hardware trace.
See [cutover checklist](MACOS-CUTOVER-CHECKLIST.md) and
[trace runbook](MACOS-TRACE-RUNBOOK.md) for the remaining sequence.
