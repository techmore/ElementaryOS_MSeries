# Wi-Fi resume recovery Rust candidate

This crate implements the behavior of the current
`mkosi.images/apple-silicon/mkosi.extra/usr/sbin/mseries-wifi-resume-fix` in
Rust. It runs only on aarch64 with the supported Broadcom PCI IDs, respects the
Wi-Fi radio state, waits 15 seconds after resume, and reloads `brcmfmac` plus
its holders only when association rejections increased or Wi-Fi remains down.

The immutable image, `omarchy-wifi-resume-fix.service`, manual recovery
installer, and live device still use the existing shell helper. The Rust
candidate is not installed or wired into suspend hooks. Do not switch those
paths until package admission, rollback, and a separately authorized device
check are complete.

## Build and parity check

```sh
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --release --locked
```

The integration suite runs the shell and Rust implementations against
independent copies of the same mock command environment. It covers architecture
and PCI gates, radio disablement, connected/disconnected/connecting Wi-Fi,
Ethernet co-presence, rejection count changes, module holders, and sleep/unload/
reload failures. It checks exit status and the exact `modprobe` calls. These
fixtures prove software behavior only; they do not qualify Broadcom firmware,
real suspend/resume, systemd ordering, or supported hardware.

The candidate uses only the standard library and forbids `unsafe` code. There
are no intentional behavior enhancements in this port so far.
