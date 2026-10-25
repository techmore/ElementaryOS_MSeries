# Touch ID on Linux: who does what (checked 2026-10-21)

Read-only survey of public repos and issues. Re-check before relying on any status. Not every fork's branches
were diffed: fork lists and last-push dates were scanned, and the SEP driver was compared in the three active
kernel trees below.

## Short answer

Touch ID on Apple silicon Linux is **Aurora's Rust `apple_sep` driver plus a patched libfprint/fprintd**, built by a
small group of contributors across three kernel trees. It works end to end on M1, M1 Pro, M2 and M2 Pro/Max Macs
in public reports. On a cold-boot M1 Pro that already used Touch ID, the `xart_guard` default that **omacom's** tree
turned on (2026-10-18) blocks matching; **SiliconForest turns it off**, and upstream's own M1 Pro runs it off.
See [XART-GUARD.md](XART-GUARD.md).

## Kernel trees

| Tree | Maintainer | Role | xART guard default | Notes |
| --- | --- | --- | --- | --- |
| [omacom/linux-aurora](https://github.com/omacom/linux-aurora) (`integration/aurora`) | Omarchy / Omacom, Aurora contributors | Official Aurora kernel, installer, releases, **issues** | **1** on M1 to M3 | Our pin (`644133b7`, #139) is here. Per-Mac report template, [CONTRIBUTING.md](https://github.com/omacom/linux-aurora/blob/integration/aurora/CONTRIBUTING.md). |
| [aurora-silicon/linux](https://github.com/aurora-silicon/linux) (`integration/aurora`, `unified-7.3/*`) | DjDeveloperr, RyanTheTide | Where SEP work is written first (issues disabled) | **1** | Ahead of omacom: Linux 7.3 Rust API adaptation, `guard existing SEP OS identity selection` (2026-10-20). Also hosts m1n1, u-boot, installer, distro repos (alarm, fedora, nixos). |
| [iconidentify/siliconforest-linux](https://github.com/iconidentify/siliconforest-linux) (`siliconforest/next`) | iconidentify; guard commit by Chris Kearney | Independent kernel with per-Mac releases (J313, J516S so far), issues enabled | **0 (off)**, by commit `ee237fd47` (2026-10-19) | Its message: existing installs' Linux records are not on the guard's list, so a guarded boot refuses them and Touch ID stops; on a cold-boot M1-family Mac keybag creation also needs a refused write. No J314S release; its notes make no Touch ID claim. |
| [AsahiLinux/linux](https://github.com/AsahiLinux/linux) | Asahi | Mainline-track | n/a | No Touch ID driver. [Matrix](https://asahilinux.org/docs/platform/feature-support/m1/): Touch ID TBA, SEP WIP. |
| [iconidentify/aurora-linux](https://github.com/iconidentify/aurora-linux) | iconidentify | Earlier reports and releases | n/a | **Archived** at 2026.10.10.12; says issues moved to omacom. Closed reports there are the best Mac-by-Mac history. |
| [t2linux](https://wiki.t2linux.org/guides/touchid/) | t2linux | Intel T2 Macs (different hardware) | n/a | Guide covers only fingers enrolled in macOS; its [state page](https://wiki.t2linux.org/state) says Not working. Undated, conflicting. |

From our pin to omacom's current head (`faed71028`, 2026-10-21) the SEP driver did not change; PR #158 (7.2.11)
does not touch it.

## Who committed SEP code (omacom `integration/aurora`, approximate commit counts on SEP paths)

| Contributor | Commits | Public repos worth watching (last push) |
| --- | --- | --- |
| iconidentify | ~230 | `siliconforest-linux`, `-m1n1`, `-mesa` (Oct 19–21); `linux-aurora-ci-sandbox`; `aurora-linux` (archived) |
| RyanTheTide (Ryan Murray) | ~108 | none public; commits land in `aurora-silicon/linux`. Author of the xART guard |
| DjDeveloperr | ~58 | `linux` fork (Oct 3), `m1n1`, `mesa`; opened omacom PR #7 |
| Chris Kearney | ~10 | via SiliconForest; author of the guard-off default and the T8112 DART DT change |
| cb2206, brentkearney, ftechhelp, JJRPF | 2–4 each | testers with `linux`/`m1n1`/`u-boot` forks; cb2206 is a J314S tester (archived #16), brentkearney J316S, ftechhelp J415, JJRPF M2 Pro |
| satchlj, joshuaswarren, scottjones, Chromatischer, jannau | 2–4 each | `aurora-linux`/`m1n1` forks and Omarchy tooling; jannau is an Asahi developer |

## Where to report

`omacom/linux-aurora` issues, using the "Aurora Linux per-Mac test report" template: one issue per Mac, later
results as comments, exact log lines, both firmware fields, the installed tag. A 2026-10-02 comment on PR #7 asked
for reports at `iconidentify/aurora-linux`; that repo is now archived, so it is superseded.
SiliconForest has its own issues if you run its kernel.

## SEP driver timeline (aurora-silicon/linux, merged)

#26 T6000 (M1 Pro) · #58 M2 Max · #152 M2 Air · #69 "Touch ID after reboot on M2 Max, M1 Pro and M1" ·
#325 recover a failed sensor registration at boot · #339 retry a failed bring-up before a verify · #346 SPI chip-select delays ·
#351/#357 hwrng across sleep · #326 refuse a damaged host-state store · **#361 xART guard on by default (2026-10-18)**.

## Per-Mac Touch ID results found (all on builds before the guard unless noted)

| Mac | Result | Source |
| --- | --- | --- |
| j313 M1 Air | enrol, verify, sudo, polkit, lock screen pass | aurora-linux#42 (archived) |
| **j314s M1 Pro 14"** | enrol, verify, reboot, resume, lock screen, polkit pass; transient attach failures incl. `sensor patch: no acknowledgment after 250 polls` (first verify's retry recovered); `xart_writes=1 j414s_persistent_enrol=1`, firmware 26.3 | aurora-linux#16 |
| j316s M1 Pro 16" | enrol, verify, verify after reboot, sudo, polkit, lock screen, one suspend pass on 11.36.1 (firmware 26.6.2); earlier sequence-counter attach failure | aurora-linux#36, #25 |
| j413 / j415 M2 Air | pass | omacom#145, aurora-silicon/linux#152 |
| j493 M2 13" MBP | pass on aurora-2026.10.17.20 | omacom#142 |
| j416s M2 Pro, j416c M2 Max | pass (j416s sepOS 27.0) | aurora-linux#8, #9; omacom#133 |
| **our j314s, firmware 27.0, 7.2.10 wip2, guard 1** | attaches; enrolment completes in the enclave but the save is refused; `matching: blocked` | XART-GUARD.md |

## Open items relevant to the J314S

- [omacom#42](https://github.com/omacom/linux-aurora/issues/42) M1 Pro SEP attach and session failures. [#23](https://github.com/omacom/linux-aurora/issues/23) sealed trusted keys. [#46](https://github.com/omacom/linux-aurora/issues/46) per-Mac provisioning.
- Not found upstream: an issue for enrolling on a guarded cold-boot Mac (our case), or for `run_enrolment` lacking the sensor bring-up retry.
- m1n1 PRs [aurora-silicon/m1n1#9](https://github.com/aurora-silicon/m1n1/pull/9) and [#6](https://github.com/aurora-silicon/m1n1/pull/6) (SEP handoff, `sep` alias) are open.
