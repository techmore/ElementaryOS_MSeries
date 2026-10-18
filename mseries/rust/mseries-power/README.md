# `mseries-power` Rust candidate

This isolated crate implements the current `mseries/power/mseries-power` CLI
contract in Rust. It is a candidate only: `enhance.sh`, the factory image,
systemd, udev, and polkit still install and invoke the existing shell program.
Do not change the default installer until parity, image admission, rollback,
and target-device qualification are complete.

## Build and parity check

```sh
cargo fmt --check
cargo test --locked
cargo build --release --locked
```

The integration suite runs both implementations against the same fake sysfs,
power-profile command, config file, and arguments. It compares success/failure
and stdout, then checks writes and persisted state. It covers all five CLI
operations, CPU caps on battery and AC, profile changes, min/max clamping,
charge thresholds and persistence, status formatting, missing sensors, invalid
commands, and sysfs write failures. This is
software parity evidence only; it does not qualify real SMC, power-profile
D-Bus, systemd, udev, polkit, or Apple Silicon hardware behavior.

## Intentional implementation changes

- The Rust version parses only known `KEY=value` settings from the root-owned
  policy file; it does not execute that file as a shell program.
- It replaces the charge-limit config atomically, retaining other lines and
  writing one `CHARGE_LIMIT` value.
- It has no third-party crates and uses no `unsafe` code.

These changes are tracked separately from behavior parity and need review
before replacing the shell implementation. Keep the deployed shell version
available for rollback until the replacement has passed an image release and
the required real-device checks.
