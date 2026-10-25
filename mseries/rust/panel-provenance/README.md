# Factory panel provenance Rust candidate

This crate implements the two commands currently provided by
`mseries/panel/verify-package-versions` and `mseries/panel/record-artifact`:

- `mseries-panel-provenance-rs verify` checks the pinned dpkg package versions,
  Wingpanel ABI path, plugin presence and SHA-256 provenance. It supports the
  existing `--only` and `--skip-plugins` options.
- `mseries-panel-provenance-rs record` records a built plugin's pinned metadata
  and SHA-256 digest using the same JSON schema as the Python command.

The Rust branch's factory build scripts now use the Rust `verify` and `record`
commands, and `stage-factory-enhancements.sh` installs the Rust executable at
the existing `verify-panel-packages` path. The executable detects that legacy
command name and runs `verify` with its original arguments. The Python sources
remain available as differential baselines and rollback sources. Full arm64
image admission has not yet passed on this branch.

## Build and parity checks

```sh
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --release --locked
python3 test-parity.py target/release/mseries-panel-provenance-rs
```

The parity harness compares both command implementations with mock dpkg-query
results and fixture plugin files. It covers version acceptance/rejection,
selective verification, package-only mode, the staged command-name invocation,
artifact creation, missing plugins, and digest mismatch. It does not replace an
actual mkosi arm64 image build.

Dependencies are Rust `serde_json` and `sha2`; `dpkg-query` remains an image-build
system tool. No intentional behavior enhancements are included.
