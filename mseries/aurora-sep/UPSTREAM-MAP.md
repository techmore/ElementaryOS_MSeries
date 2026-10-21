# Touch ID on Linux: who does what (checked 2026-10-21)

Read-only survey of the public repos. Re-check before relying on any status.

## Repositories

| Repo | Role | State |
| --- | --- | --- |
| [omacom/linux-aurora](https://github.com/omacom/linux-aurora) | Aurora kernel, installer, releases, **issues** | Active. Default branch `integration/aurora`. Per-Mac report template and [CONTRIBUTING.md](https://github.com/omacom/linux-aurora/blob/integration/aurora/CONTRIBUTING.md): one issue per Mac, later results as comments, quote exact log lines, both firmware fields, the installed tag. |
| [aurora-silicon/linux](https://github.com/aurora-silicon/linux) | Source of the SEP driver PRs (issues disabled) | Active. SEP driver is Rust: `drivers/soc/apple/sep.rs`, `sbio.rs`, `xart_guard.rs`. |
| [aurora-silicon/m1n1](https://github.com/aurora-silicon/m1n1) | Bootloader work (SEP handoff, `sep` alias) | Open PRs #9, #6. |
| [iconidentify/aurora-linux](https://github.com/iconidentify/aurora-linux) | Earlier reports and releases | **Archived**, frozen at 2026.10.10.12; says issues and releases moved to omacom/linux-aurora. Its closed reports are the best j314s history (#16, #13, #24, #27). A 2026-10-02 comment on omacom PR #7 asked for reports there; that is superseded by the archive notice. |
| [AsahiLinux/linux](https://github.com/AsahiLinux/linux), [docs](https://asahilinux.org/docs/platform/feature-support/m1/) | Asahi | Matrix lists Touch ID TBA and SEP WIP; SEP page is research notes. No Touch ID driver upstream. |
| [t2linux](https://wiki.t2linux.org/guides/touchid/) | Intel T2 Macs (different hardware) | Guide covers only fingers already enrolled in macOS; its [state page](https://wiki.t2linux.org/state) says Not working. Undated, conflicting. |

## SEP driver timeline (aurora-silicon/linux, merged)

- #26 T6000 (M1 Pro) support · #58 M2 Max · #152 M2 Air · #69 "Touch ID after reboot on M2 Max, M1 Pro and M1"
- #325 recover a failed sensor registration at boot (CLEAR_STATE retry) · #339 retry a failed bring-up before a verify
- #346 SPI chip-select delays for the sensor · #351/#357 hwrng across sleep · #326 refuse a damaged host-state store
- **#361 xART guard, on by default on M1/M2 (2026-10-18)**, documented in `XART-SAFETY.md`.

Our pin (`644133b7`, merged #139) includes #361. From that pin to current `integration/aurora` (`faed71028`,
2026-10-21) the SEP driver did not change, and upstream PR #158 (7.2.11) does not touch it.

## Open items relevant to the J314S

- [omacom/linux-aurora#42](https://github.com/omacom/linux-aurora/issues/42) M1 Pro SEP attach and session failures (J314S transient attach failures).
- [#23](https://github.com/omacom/linux-aurora/issues/23) sealed trusted keys through keybag saves. [#46](https://github.com/omacom/linux-aurora/issues/46) per-Mac provisioning.
- Not found upstream: an issue for enrolling on a guarded cold-boot Mac (our case, see `XART-GUARD.md`) or for `run_enrolment` lacking the sensor bring-up retry.

## J314S history

[iconidentify/aurora-linux#16](https://github.com/iconidentify/aurora-linux/issues/16) (archived): Touch ID enrol, verify,
reboot, resume, lock screen and polkit passed on pre-guard builds with `xart_writes=1 j414s_persistent_enrol=1`;
three kinds of transient attach failure, including `sensor patch: no acknowledgment after 250 polls`, which the
first verify's retry recovered. System firmware there was 26.3; ours is 27.0.
