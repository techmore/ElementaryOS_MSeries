# Omnissa Horizon Client (x64, emulated)

Omnissa publishes no arm64 Linux Horizon Client: the 2606 tarball has x64 and 32-bit armhf only, and Apple silicon
cannot run armhf. The source is closed, so there is nothing to port. `install-horizon-client.sh` runs Omnissa's
own x64 client under FEX inside a 4 KB-page microVM, using the muvm setup from `install-muvm.sh`.

    bash mseries/install-muvm.sh            # once
    bash mseries/install-horizon-client.sh  # install to ~/.local/opt/omnissa-horizon
    horizon-client-x64 -s broker.example.com
    bash mseries/install-horizon-client.sh --uninstall

- Download: `Omnissa-Horizon-Client-Linux-2606-8.19.0-32216036411.tar.gz` from download3.omnissa.com (about 341 MB),
  sha256 pinned in the script (it matches the Arch AUR pin). Nothing proprietary is committed to the repo.
- Four Ubuntu 24.04 x64 libraries the FEX rootfs lacks (libxkbfile, libpcsclite, libv4l, lttng-ust and their
  dependencies) are fetched with pinned sha256s into `extra/`. `liblttng-ust.so.0` is not provided; only the
  optional `horizon-client-next` bundle needs it.
- muvm allows one VM at a time (`muvm.lock`); a second `muvm` call prints nothing while another runs.

## Verified 2026-10-18
`horizon-client-x64 --help` prints the client's usage through FEX/muvm. Not tested: opening the GUI, logging in to a
broker, Blast or PCoIP sessions, USB redirection, audio, performance under emulation. Until those are checked,
`horizon-rdp` ([HORIZON-RDP.md](HORIZON-RDP.md)) remains the tested-to-install fallback.
