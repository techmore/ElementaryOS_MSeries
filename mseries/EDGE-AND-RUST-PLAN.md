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

## 2. Port our code to Rust

The later owner decision in `OMARCHY-M-ROADMAP.md` governs: integrate and qualify
first, then inventory and migrate the maintained implementation to Rust. The
older candidate ordering below is advisory; its exclusions are superseded.
Performance improvements require measurements.


Inventory (tracked files, excluding `repos/`): about 6,000 lines of shell, 4,800 Python,
1,800 Vala, no Rust. Rust 1.99 is installed on the M1 Pro.

Port where Rust buys safety or speed; leave glue alone. "All of it" is not recommended:
rewriting installer shell and Vala patches would add risk and no security, and the Wingpanel
and Gala patches must stay in Vala to keep applying to upstream.

| Order | Component | Why | Notes |
| ---: | --- | --- | --- |
| 1 | `mseries-power` (root, run through pkexec/polkit) | Privileged, input-handling | Smallest, best first port |
| 2 | `mseries-wifi-resume-fix` (root) | Privileged; had a real bug today | Behaviour tests already exist |
| 3 | `netusage` logger (SQLite, DNS events) | Parses untrusted network data | Also faster |
| 4 | brightness bridge, keyboard backlight (D-Bus services) | Always running | zbus |
| 5 | launcher, troubleshooter UI | GTK4 UI | gtk4-rs; lowest priority |
| - | `install-*.sh`, `elementary-grow.sh`, mkosi glue | Orchestration | Stay shell |
| - | Wingpanel/Gala Vala and patches | Must match upstream | Stay Vala/C |

Rules for each port: write parity tests against the current behaviour first; ship side by
side and switch over only after the tests and a real-hardware check pass; build for aarch64
in CI; `cargo audit` and `cargo deny` in CI; no `unsafe` without a written reason; benchmark
before and after with `mseries/benchmarks/`; keep the old script until a release has passed.
