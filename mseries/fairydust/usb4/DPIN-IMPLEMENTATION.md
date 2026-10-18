# T6000 DP-IN implementation draft — DeepSeek / Codex handoff

2026-10-16. **Source implemented and offline checked; hardware untested.**
No kernel/module/DTB was installed or loaded by this implementation work.
The M1 Pro was not rebooted and no cable was moved. The owner's current
no-install/no-reboot/no-unplug constraint remains in force.

Start with [STATE-OF-PLAY](STATE-OF-PLAY.md) for the actual hardware frontier.
The separately recorded HPD adapter-selection test moved the tunnel to
`0:5 <-> 1:14`; DPRX still timed out. That earlier live change is independent
of this offline DP-IN series. Do not count a build or a decompiler result as
monitor wake, EDID detection or pixels.

## Concrete changes available for review

Keep `0003-dp-out-prefer-adapter-with-hpd.patch`. Apply these additional
patches, in this order, to fairydust
`ce9f2eba72c061a50b2d790450e90af3439d8c24` after
`0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch` and
`0002-experimental-dp-tunnel.patch`:

1. `0004-experimental-dpin-bindings.patch`: a separate DP-IN PHY binding
   and child nodes accepted by the ACIO parent binding.
2. `0005-experimental-dpin-handshake-tunnel-clocks.patch`: new DP-IN
   provider, ATC tunnel-clock API, DCP callback/error/HPD integration and
   offline tests of the actual production helpers/functions.
3. `0006-experimental-j314s-dpin-wiring.patch`: ACIO1 DP-IN resources
   `0xb01e50000` / `0xb01e58000`, size `0x4000`, IRQ 1354/1355,
   ATC1 DP-interface references. Only DP-IN0 is enabled for the existing
   j314s experimental tunnel macro; DP-IN1 and control boards stay disabled.

The separate `0002-avd-job-segments-use-kvmalloc.patch` is unrelated and is
not a substitute for `0002-experimental-dp-tunnel.patch`. Stable `PKGBUILD`
and stable kernel configuration have not been changed to auto-apply this
experiment.

The DP-IN provider reserves a USB4/TBT-mode ATC tunnel without configuring
physical DP lanes or external AUX. Activation clears inactive bit 0 at
`+0x0c`, polls ACK at `+0x10`, and checks HPD bit 2 at `+0x00` while pending.
Deactivation requests inactive and waits for its ACK even with HPD low.
The threaded IRQ handler reads status/HPD/status (`+4/+0/+4`) until stable,
acks the captured values and forwards notifications through deferred DCP
work. An unstable IRQ is bounded and masked rather than allowed to storm.

DCP ACTIVATE/DEACTIVATE own PHY power; SET_LINK_RATE owns the tunnel clock
configuration. Rates 1620/2700/5400/8100 Mb/s select PCLK 4/3/1/0. Both
DP-IN clocks share a fixed AUSPLL descriptor; the second client does not
retune it and the last client stops it. Initialization merely reserves the
PHY: Apple's T6000 `initDPTunnel` is a no-op. Existing USB4 common power/CIO
PLL support remains in place. APB command and lock failures propagate;
rollback/shutdown failures preserve ownership and block new activation.

DCP connect/validate low-word attributes are `0x101` for DP-IN (role 1 plus
HPD support), with the current core0/ATC1/die0 target retained. Physical DP
keeps its previous attributes. The old null-PHY/fake-success path is removed.
Link completion requires successful activation plus nonzero rate and lanes;
transport, firmware and PHY errors are returned. Disconnect cancels HPD
work and balances ownership. System suspend is refused while this
experimental provider is initialized; suspend/resume is unqualified.

## Evidence, and what the code does not yet prove

[REA findings](REA-DPIN-FINDINGS.md) record the exact Apple inputs, original
instruction checks and authenticated virtual-call targets.
[Ghidra second pass](evidence/2026-10-16-ghidra-dpin-crosscheck.md) independently
corroborates the handshake, IRQ and clock routines. This is original Linux
implementation based on derived behavior; proprietary binaries and complete
Apple decompiler output are not published.

**The remaining lifecycle question is material:** the Linux router's DPRX
wait and DCP activation must be ordered correctly. This draft starts DP-IN
on the DCP firmware ACTIVATE callback. It does not add a Thunderbolt
connection-manager hook to guarantee activation before an unbypassed DPRX
wait. The existing manual force-link entry remains for a future controlled
experiment. HPD alone does not automatically connect DCP: it does not prove
which router tunnel is allocated. Do not declare the full tunnel protocol
implemented or assume a dependency cycle has been resolved.

### Linux call order established from the pinned source

The source narrows the ordering question further:

- `tb_tunnel_one_dp()` allocates the tunnel with callback
  `tb_dp_tunnel_active`, then calls `tb_tunnel_activate()`.
- `tb_tunnel_activate()` runs DP capability exchange/CM handshake, activates
  the paths, and calls `tb_dp_activate(true)`.
- `tb_dp_activate(true)` programs HopIDs and enables both adapters, then
  calls `tb_dp_dprx_start()`. Because this tunnel has a callback, it queues
  DPRX work and returns **-EINPROGRESS**; it does not block until completion.
- `tb_dp_dprx_work()` polls DPRX in 25ms attempts separated by 50ms scheduling
  delays, with a default 12-second overall deadline. Only success marks the
  tunnel active. The final callback then handles bandwidth or tears it down.
- This Thunderbolt path contains no call into Apple DCP connection setup.
  DCP starts via the existing debugfs force-link/OOB-hotplug path; the
  ordinary Type-C DP-altmode hotplug path is not a USB4 tunnel-start signal.
  DP-IN IRQ forwarding in the draft begins only after DCP connects and
  initializes the provider.

Thus there is **no automatic start bridge** in this draft, and activation
is asynchronous rather than a proven unavoidable synchronous deadlock.
A manual DCP start could overlap the DPRX window, but has not been qualified.
Waiting for `tb_dp_tunnel_active()` success before first starting DCP would
be too late if DPRX depends on DCP. A candidate future notification boundary
is after both DP adapters are enabled, before DPRX work starts. It needs an
explicit, lifetime-safe host DP-IN-to-DCP mapping, work outside `tb->lock`,
and matching teardown; do not call blocking AFK requests under that lock or
use bare HPD/guessed host-port numbers as a substitute. ACIO depopulates its
children on shutdown, so provider/consumer removal also needs qualification.
These are design constraints from source, not a new tested hardware result.

Other unqualified areas: live boot-patched ADT/resource ownership, opaque
ACIO `startUsingTunnel` effects versus existing Linux routing, firmware
callback ordering, failed-teardown/device-removal races, runtime PM, distinct
IRQ-HPD pulses/MST, EDID, video and suspend. IRQ-HPD currently queues a real
HPD-level read; it is not a qualified MST interrupt implementation. The
shipped j314sap metadata is board evidence, not a live register trace.

## Reproduce offline checks (no root, no installation)

Use a fresh pinned source tree and a separate build directory. Apply the
named patches above; never patch the running installation. Set `USB4` to
this repository's `mseries/fairydust/usb4` directory, `SRC` to the patched
kernel source and `OUT` to a scratch output directory. The commands below
are build/test operations only:

```sh
mkdir -p "$OUT"
cp "$USB4/config" "$OUT/.config"
"$SRC/scripts/kconfig/merge_config.sh" -m -O "$OUT" \
    "$OUT/.config" "$USB4/dpin-offline.config"
make -C "$SRC" O="$OUT" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$SRC" O="$OUT" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- prepare
make -C "$SRC" O="$OUT" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- W=1 -j4 \
    drivers/phy/apple/ drivers/gpu/drm/apple/ \
    apple/t6000-j314s.dtb apple/t6001-j314c.dtb
cd "$SRC"
gcc -std=gnu11 -Wall -Wextra -Werror -fsanitize=undefined \
    -Idrivers/phy/apple tools/testing/apple-dpin/dpin-offline.c \
    -o "$OUT/dpin-offline"
"$OUT/dpin-offline"
python3 tools/testing/apple-dpin/test-clock.py .
python3 tools/testing/apple-dpin/test-connection.py .
python3 tools/testing/apple-dpin/test-dtb.py \
    "$OUT/arch/arm64/boot/dts/apple/t6000-j314s.dtb" \
    "$OUT/arch/arm64/boot/dts/apple/t6001-j314c.dtb"
dt-doc-validate Documentation/devicetree/bindings/phy/apple,t6000-dpin.yaml \
    Documentation/devicetree/bindings/thunderbolt/apple,t8103-usb4-acio.yaml
dt-mk-schema -j -o "$OUT/dpin-schema.json" \
    Documentation/devicetree/bindings/phy/apple,t6000-dpin.yaml \
    Documentation/devicetree/bindings/thunderbolt/apple,t8103-usb4-acio.yaml
dt-validate -s "$OUT/dpin-schema.json" -l apple,t6000-dpin \
    "$OUT/arch/arm64/boot/dts/apple/t6000-j314s.dtb"
```

Normal kernel C-build tools, ARM64 GCC, Python, GCC, libfdt and dtschema are
needed. On this machine missing bison/flex/m4 and schema dependencies were
staged in isolated scratch directories; no system packages were installed.
RUST/BTF were disabled only for this C-build check. It does not qualify the
production Rust/BTF configuration.

Results: **11 handshake/IRQ helper groups + 11 production-clock groups +
7 production-EPIC connection groups, and 2 compiled-board wiring checks**.
ATC/DP-IN relocatable module objects and the complete `appledrm.o` linked;
both DTBs compiled. Binding document validation and DP-IN-filtered DTB
schema validation passed. Existing DCP kernel-doc and unrelated DTS warnings
remain. Checkpatch reports zero errors and only generic new-file MAINTAINERS
warnings on the binding/code patches. The reconstructed patch series
byte-matches the reviewed source. See the
[machine-readable validation record](evidence/2026-10-16-dpin-offline-validation.json).

No full kernel Image, final `.ko`/MODPOST, production-config build, hardware
locking/concurrency test, or display success is claimed. Fake MMIO tests
exercise source logic; they cannot establish actual register behavior or
firmware scheduling. Configured OpenCode's scoped build-log review also
identified the distinction between object/DTB checks and full kernel/runtime
qualification; it did not perform a hardware test.

## Coordination correction for the concurrent host-stack draft

A concurrent `evidence/2026-10-16-host-stack-decomposed-dpin-and-crossbar-routing.md`
draft was observed after this series landed. Its register interpretation and
"PHY was never the wall" conclusion are superseded by the original-byte,
dispatch and Ghidra checks here. Existing common wake/lane-mode definitions
are not proof that experiment 2's null-PHY callback path programs tunnel
PCLK/AUSPLL. `+0x04` is IRQ status, not the handshake; clearing `+0x0c` requests
activation, and ACK is `+0x10`. Do not build a driver from those older guesses.

The candidate compiled j314s DTB was also explicitly checked: the tunnel's
mux phandle resolves to `/soc/mux@b0304c000`, **status okay**, control index 1.
This is an offline artifact result, not a claim the running boot.bin contains
that tree. Keep runtime DT, source DT and compiled candidate distinct. Do not
repack/install boot.bin or reboot under the current constraint. The concurrent
draft was left untouched; reconcile it against this handoff before publishing
its conclusions or starting another implementation of the same provider.

## Next task for DeepSeek / Codex — advance the recorded frontier

1. Review the actual new series, not the superseded guess that `+0x04` is
   the handshake or that writing `+0x0c = 1` activates DP-IN. Correct semantics
   are above and in the independent RE report.
2. Resolve router/DCP activation ordering and ACIO tunnel-use ownership by
   tracing the pinned Linux call path and the already acquired Apple inputs.
   Do not repeat binary discovery, port guessing or change physical cables.
   Identify an explicit integration hook if DPRX waits before ACTIVATE.
3. Complete a normal configuration/MODPOST build before proposing a live
   deployment. A successful module-only Thunderbolt test does not establish
   that a newly introduced PHY plus changed DTB can be deployed that way.
4. Only after the owner changes the current hardware constraint, propose one
   bounded experiment with a precondition, exact action, captured logs and
   rollback. First verify DP-IN ACK/clock lock; then demand unbypassed DPRX
   completion, EDID/modes, and a visible picture, in that order. Visible
   monitor wake is a useful observation but does not by itself prove a link.

Every future session must record its tested patch revision, actual action,
observed ACK/clock/DPRX/EDID/picture results and the next unresolved condition.
Do not restart the same discovery work or label static evidence a solved
hardware path.
