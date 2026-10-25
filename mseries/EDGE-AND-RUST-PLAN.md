# Plan: stay within 24 h of upstream, and move our code to Rust

Requested 2026-10-14. Both are large; this is the proposed shape, not work done.

## Rust branch direction — 2026-10-17

The owner now wants a dedicated `rust` branch that treats every upstream project
and every M-series-owned customization as a separately tracked migration item,
with feature parity as the conversion gate and deliberate enhancements recorded
separately. The branch starts from `origin/main`; its living inventory and
acceptance rules are in [`rust/README.md`](rust/README.md).

“Every project has an item” means every source project gets an independently
reviewable record: upstream and revision, current implementation boundary,
features to preserve, local patches, update cadence, and Rust/retain/replace
decision. It does not mean copying all upstream projects into one Rust
workspace. Keep upstream source and licenses at their pinned revisions, keep
Linux kernel and desktop protocol boundaries intact, and migrate the M-series
code around them one independently shippable component at a time. Where an
upstream component is explicitly selected for replacement, it gets its own
crate/package and an adapter boundary so upstream updates cannot silently
change the port.

The `rust` branch is a migration lane, not a claim that an entire Linux OS can
be safely rewritten in Rust. The bootloader, Linux kernel, systemd, elementary
OS/Pantheon and many drivers remain upstream projects with their own languages
and release contracts. Their Rust-branch records explain their boundary and
parity obligations; they are not vendored or rewritten by default. This keeps
daily/weekly upstream tracking feasible while allowing intentional Rust
enhancements to be proposed as distinct, measurable changes.

## 1. Within 24 hours of upstream, maximum bleeding edge

Meaning: we learn about and build upstream changes within a day. We do **not** auto-deploy
them to the daily-driver MacBook: kernel, m1n1, bootloader and audio changes can leave it
unbootable or damage the speakers, and `AGENTS.md` forbids changing the owner's bootloader,
kernel or running audio stack as part of image work.

1. **Detect (done):** `upstream-watch.py`, `touchid-watch.py`, `people-watch.py`.
2. **Candidate (next):** a daily CI job on a self-hosted or GitHub runner that, for each
   tracked source (AsahiLinux/linux `fairydust`, m1n1, Mesa Asahi, elementary/os `main`,
   omarchy-mac-pkgs), opens a PR bumping the pin in `UPSTREAM-PINS.md`, builds the kernel
   package and the image, and runs the QEMU smoke test. Never pushes to `main` on its own.
3. **Edge lane:** an `edge/*` branch and an opt-in mkosi profile so a candidate can be booted
   from a spare partition or VM. Promote to the Mac only with: smoke test green, stock Asahi
   recovery entry kept (commit aa5e8d1), the owner's go-ahead.
4. **Limits:** upstream breakage is expected on the edge lane; SSPL and sponsor-only code is
   never imported; every bump records the exact revision.

## 2. Port the maintained implementation to Rust

The owner has clarified the target: migrate the full executable implementation
maintained by this project, including installer and image orchestration, to
Rust. Keep each component separate and preserve its interfaces. Required config
formats and upstream patches may remain in their native formats only where
their consuming project requires it; record every such exception. The kernel,
firmware, elementary OS, and other external projects remain distinct upstream
projects with their own languages, licenses, pins, and release contracts. Do
not describe those projects as locally rewritten.

The first migration record and proof-of-concept is
[`rust/mseries-power/`](rust/mseries-power/). Its independent binary is not
installed by default. Thirteen differential scenarios pass against the current
shell command; the remaining owned-code inventory, migration sequence, source
update candidate workflow, package integration, and device qualification are
still open. The earlier recommendation to leave shell installer/image glue
permanently in shell is superseded by this direction.

Rules for each port: establish the exact old contract; write differential
parity checks; preserve separately recorded intentional enhancements; build
ARM64 in CI; review dependencies and licenses; use no `unsafe` without a
written reason; test failure recovery and rollback; and keep the old
implementation through a qualified release. Measure before/after behavior
where it matters. Compilation alone is not parity, and fake sysfs/VM results do
not establish hardware qualification.
