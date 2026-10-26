# Home Storage developer path

This read-only example reports usage of the filesystem containing the current
user's home folder. It demonstrates one bounded asynchronous service call,
duplicate-submit prevention, a useful error and retry. It does not scan files,
remove data or start a background service. Closing the accepted window cancels
an unfinished check through Host process ownership.

Status: description/rules and actual command failure/recovery are tested on
macOS. The new example's native Linux build, keyboard journey, screenshots,
packaging and measured developer trial remain pending. Earlier settings-app
qualification is separate evidence and does not qualify this new UI.

From a checkout on a Linux GTK 4.20+ development host with Rust 2024, GTK/Wayland
headers, pkg-config and wayland-scanner already provisioned:

```sh
python3 mseries/sdk-tests/prepare.py /tmp/home-storage-sdk
cargo run --manifest-path /tmp/home-storage-sdk/Cargo.toml -p msdk -- \
  check /tmp/home-storage-sdk/msdk/examples/home-storage.ui.json
cargo run --manifest-path /tmp/home-storage-sdk/Cargo.toml -p msdk -- \
  gen /tmp/home-storage-sdk/msdk/examples/home-storage.ui.json \
  /tmp/home-storage-app --sdk-root /tmp/home-storage-sdk
cargo test --manifest-path /tmp/home-storage-app/Cargo.toml
cargo run --manifest-path /tmp/home-storage-app/Cargo.toml
```

Use new output directories: generation deliberately refuses to overwrite an
existing project. Click **Check again**. While work is pending, the action is
hidden and the app explains that closing the window cancels the operation.
On success, it displays `df -h` output and identifies the result as filesystem
usage, rather than claiming this is a size calculation of the home folder.

To review an unavailable backend without invoking a real command, create a
fixture containing `{"calls":{}}` and use the preview runner:

```sh
printf '%s\n' '{"calls":{}}' > /tmp/home-storage-unavailable.json
cargo run --manifest-path /tmp/home-storage-sdk/Cargo.toml -p msdk-gtk --bin msdk-run -- \
  /tmp/home-storage-sdk/msdk/examples/home-storage.ui.json \
  --fixture /tmp/home-storage-unavailable.json
```

The fixture provider must return unavailable without falling through to the
actual command. Check again remains available after failure. Run the app without
the fixture to exercise recovery against the real read-only command. Fixture
results are synthetic; do not report them as real backend qualification.

`cargo test -p msdk --test golden_path` checks rules, visible recovery text,
duplicate calls and model generation. On Linux/macOS it also executes the exact
command with a child-only missing HOME, handles its actual nonzero error, and
retries with the real environment. It does not log home paths or mount output.
Native Host version/denial/malformed-result/fixture/no-fallback/close tests are
documented in SDK-RUNTIME-CONTRACT.md. Native golden-path UI qualification must
still use this exact description and a source-matched generated executable.

Retain coding time separately from provisioning, download, compilation, queues
and wall time. The <=30-minute developer target needs a measured clean trial;
these commands and automated checks alone do not establish that result.
