# iconidentify repository screen — 2026-10-12

Scope: public repository metadata for all 35 repositories, with targeted README review of maclab, omarchy-m1-video, chonkstep and its agent broker, imac19-1-linux, and Aurora release metadata. This is a compatibility screen, not source-level qualification or a hardware test.

## Priority candidates for elementary on M1 Pro

| Project | Value | Integration boundary / next check |
| --- | --- | --- |
| [Aurora](https://github.com/omacom/linux-aurora) | Active Apple Silicon kernel development, including display/dock work | iconidentify/aurora-linux is archived and frozen at 2026.10.10.12. Active upstream release checked: 2026.10.11.15. Compare M1 Pro T6000/J314s changes with our pinned fairydust USB4 kernel and boot chain before staging a separate test kernel. Latest historical display release validates M3 Pro dock output and M1 Air direct output, not our M1 Pro dock. Keep our known-good boot path. |
| [maclab](https://github.com/iconidentify/maclab) | One-shot kernel tests, baseline comparisons, logs and crash recovery | GRUB/Limine boot adapters and Arch packaging need inspection against our actual boot layout. GUI tests target Hyprland and need Pantheon equivalents. Baseline intentionally reboots twice; do not invoke setup or baseline during ordinary desktop use. Out-of-band recovery requires additional hardware/controller. |
| [omarchy-m1-video](https://github.com/iconidentify/omarchy-m1-video) | AVD kernel robustness fixes and a patched VA-API bridge for H.264/HEVC/VP9 | Strong candidate for our video decode backlog. Installer uses pacman, linux-asahi headers, hooks and a boot service; translate packaging rather than run it on Ubuntu. Upstream tested T8103 M1, not T6000 M1 Pro. Check firmware/device readiness, kernel patch overlap and libva ABI first; qualify an isolated bridge build and matched module before enabling at boot. Upstream records unresolved decode cases and historic hard resets. OpenGL output is its documented mpv workaround for imported-frame Vulkan problems. |
| [Chonk Agents](https://github.com/iconidentify/chonkstep/tree/main/examples/chonk-agents) | A separate local broker for Codex/Claude/OpenCode activity, bounded event snapshots and lifecycle tracking | Most interesting desktop port: adapt the broker protocol to a native Wingpanel frontend. Session activity complements quota data; it does not supply token budgets. Existing navigation depends on verified Wayland/terminal bindings and must be adapted to Gala. Inspect hooks and OpenCode configuration compatibility before installing. No compositor replacement is needed to study the separate broker. |
| [omarchy-m-testing fork](https://github.com/iconidentify/omarchy-m-testing) | Hardware regression coverage and baseline reports | Follow maintained upstream referenced by maclab (maralcbr/omarchy-m-testing); separate package/distro expectations from hardware assertions. Keep report publication opt-in. |
| [m1n1 fork](https://github.com/iconidentify/m1n1) | Boot-chain research | Inspect fork delta and required kernel/firmware coupling; no blanket bootloader update. |

## Other repositories

- **Omarchy packaging/reference:** omarchy, omarchy-mac-pkgs, omarchy-pkgs, omarchy-pkgs-aarch64. Useful for recipes and version pins; Arch packages are not elementary packages.
- **Optional UI inspiration:** chonkstep is an alpha Hyprland-compatible compositor, not a Gala plugin. Its bounded rendering and Mac interaction documentation can inform separate research. omeyes is a QML Omarchy bar plugin and needs a Wingpanel port. omatune is an optional terminal tuner, not a base OS fix.
- **Wrong hardware:** imac19-1-linux targets an Intel 2019 iMac with different audio/Wi-Fi/Bluetooth hardware. Do not apply its CS8409 DKMS module, board firmware or Bluetooth pairing workaround to this M1 Pro.
- **Optional applications/research:** auteur, browser-qemu, cartograph, chonkcraft, chonkline, jamedit, pufflehuck, ttfx, vkQuake, hermes-agent. Assess individually if requested; no demonstrated base-image hardware benefit from this screen.
- **Retro computing/AOL projects:** atomforge, atomforge-fdo-c, atomforge-fdo-java, aux-c89-summer, chonkblocker-retro-downloads, dialtone, fdo88_docs, musick, se30-linux, se30boot, se30os, wiretap. Outside this build’s immediate hardware/desktop scope.

## Recommended sequence

1. Compare active Aurora source and feature documentation against our exact M1 Pro kernel and existing USB4 patches; establish model-specific evidence for display and SEP features. No Touch ID login claim follows from the release summaries reviewed here.
2. Review and stage the video bridge/AVD work using our matching kernel build and a reproducible Debian-family packaging path.
3. Prototype the independent agent broker with a native elementary frontend after reviewing its hooks and navigation contract.
4. Adapt maclab recovery and baseline testing before broad kernel experiments.

No installer, provider hook, boot setting or running kernel was changed by this review.
