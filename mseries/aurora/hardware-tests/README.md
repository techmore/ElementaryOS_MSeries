# Hardware test receipts and release freezes

Hardware labels belong to an exact board + kernel image + selected module/DTB
hashes + m1n1 boot-payload hash + runtime feature parameters. Tests on a J316S
are not automatically J314S tests. A successful compile, a bound driver and a
successful suspend are separate results.

Current recorded release:

| Kernel | Board | Result | Release status |
| --- | --- | --- | --- |
| Aurora `.20`, `7.1.12-2-20261017.20-sep-ARCH` | Local J314S/M1 Pro | Boot observed >5 min, PMP ready/started/owns fabric, idle counters advance, selected severe-log scan clear | [Frozen experimental exp1](../frozen/mseries-aurora20-j314s-2026.10.18-exp1.json); incomplete qualification |
| Aurora `.19` with historical hand-patched boot payload | Local J314S/M1 Pro | Historical hangs/probe failures in `AURORA-SECOND-BOOT.md` | Rejected for promotion; historical evidence, no new test receipt |
| `.20-enh1` / `-egpu` | ARM64 CI | Prior native builds passed; new integrated build checked by CI | Hardware untested |
| `7.2.10-elementary-aurora72-wip1` | Pinned PR #139 snapshot | Prepared; 12 PMP production host tests passed; native build in CI | Hardware untested; upstream contributor reports remain separate |

Additional local [smoke receipt](2026-10-18-j314s-aurora20-smoke.json), recorded
after the exp1 freeze: the real Apple M1 Pro G13S C0 rendered a GLES shader and
all 16 RGBA pixels read back correctly (Mesa 26.0.8); a 1 MiB temporary-file
fsync/SHA256 readback also passed. These are scoped smoke tests, not GPU soak,
full storage/suspend/recovery qualification, or power comparisons. Exp1's frozen
assets and original tested-scope list remain unchanged; future evidence belongs
to a new freeze ID.

Reproduce without a display-mode change or destructive disk testing:

```sh
python3 mseries/hardware/kernel-smoke.py --receipt /absolute/work/j314s-test.json \
  --work /absolute/work --output /absolute/work/j314s-smoke.json \
  --kernel-image /boot/vmlinuz-aurora-sep-20261017.20 --boot-image /boot/m1n1/boot.bin
```

It requires a C compiler and EGL/GLES development files. It verifies the live
boot, module/DTB and kernel/boot-file hashes and feature parameters before testing,
and refuses a software renderer. Output receipts are never overwritten.

## Collect without changing the machine

Save the current kernel journal as JSON into a private work directory. The
collector checks its `_BOOT_ID` against the live boot before reading readiness
messages. Pass the exact kernel/boot payload files explicitly:

```sh
sudo journalctl -b -k -o json --no-pager > /absolute/work/kernel.jsonl
python3 mseries/aurora/qualification.py collect --duration 30 \
  --kernel-image /boot/vmlinuz-aurora-sep-20261017.20 \
  --boot-image /boot/m1n1/boot.bin --kernel-log /absolute/work/kernel.jsonl \
  --output /absolute/work/j314s-test.json
```

It records SMC total-system power samples, median and p10/p90, per-CPU idle
counter deltas, power source, brightness, connector enumeration, active
Mutter/Gala modes (refresh/VRR selection), display power mode, cpufreq,
module parameters and selected artifact hashes. It performs no boot, suspend,
sensor probe, disk workload, display-rate change or audio change. Kernel-log
UUIDs/addresses and full command lines are not copied into the public receipt;
the current-boot ID and whitelisted feature flags are retained. Module hashes
describe installed files; they do not prove a module was not replaced on disk
after it was loaded. Kernel image identity describes the explicit boot file.
Archive the corresponding original package as well when freezing distribution.
The [binary verification](2026-10-18-j314s-binary-verification.json) confirms
that the observed boot image, appledrm/SEP module files and J314S DTB exactly
match entries in the checksum-pinned published `.20` package. CI verifies that
proof against the receipt and upstream pins with `--binary-proof`.

The first capture occurred during agent/source activity. Its power reading is
an uncontrolled observation. Exp1 predates active refresh capture; its connector
mode list describes available modes, not selected refresh. Its original evidence
remains immutable. New captures read active modes with a bounded read-only
D-Bus call, omitting monitor serials. Missing session-bus/mode data blocks stable
promotion. A later read-only diagnostic found built-in fixed 120 Hz and external
1080p fixed 60 Hz; it does not establish exp1's original refresh configuration.
`controls_unchanged` verifies configuration,
not a matched workload or an idle session. No efficiency claim follows.

## Freeze and verify

```sh
python3 mseries/aurora/qualification.py freeze --id NEW-LOWERCASE-RELEASE-ID \
  --evidence /absolute/work/j314s-test.json --output /absolute/work/frozen.json
python3 mseries/aurora/qualification.py verify /absolute/work/frozen.json \
  --evidence /absolute/work/j314s-test.json
```

`python3 mseries/aurora/check_freezes.py --base BASE_COMMIT` also rejects
changes or deletion of existing frozen manifests/pin snapshots relative to the
reviewed Git base. CI runs this history guard. Archived pin bytes in
`frozen/pins/aurora20.json` keep exp1 verifiable when the active `release.json`
advances; use `--pins` with that snapshot for historical verification.

Default channel is experimental. Existing outputs are refused. A published
release ID is immutable: new bits, configuration or evidence produce a new
release. Verification recomputes the complete manifest and rejects manually
edited qualification labels, changed pins/evidence or mixed identities.

Stable promotion requires pass evidence for boot, graphics, GPU, storage,
network, input, suspend/resume, recovery, thermal and paired energy tests, no
failed case, three distinct boots, at least three sleep cycles and three
alternating AB/BA power pairs with matching control digests. Each pair requires
positive finite measured medians and must stay within a 10% regression budget.
The acceptance budget is not a claimed improvement. `energy_ab` records use
`successful_cycles`, plus a `pairs` list with `order`, `baseline_controls_sha256`,
`candidate_controls_sha256`, `baseline_median_w` and `candidate_median_w`.
Retain raw benchmark evidence and human verification notes with those records.
The read-only collector never manufactures these active-test results.

The measured `.20` baseline is pinned by `release.json`. Source candidates
need their own build-provenance/pin record with the matching `kernel_release`;
using the baseline pins for a candidate fails admission. No freeze command
installs a kernel, changes a boot entry or promotes an experimental default.
