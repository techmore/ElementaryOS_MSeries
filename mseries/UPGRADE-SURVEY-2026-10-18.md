# Packaging upgrade survey, WIP branches and the Aurora Silicon "beta" lanes — 2026-10-18

Claude Code, read-only survey at about 10:30 UTC. Branch `claude/upgrade-survey`, cut from `main` `a197695`.
No kernel, bootloader, m1n1, ESP, apt package or audio change was made, and nothing was installed or rebooted.
The `codex/aurora-enh1-boot-trial` branch and the CodexBar pin were not touched. The CodexBar pin is reported only.

## 1. The "other beta kernel group": Aurora Silicon (`aurora-silicon/linux`)

**This is the group the owner remembers.** [Aurora Silicon](https://github.com/aurora-silicon) is a GitHub
organization whose kernel tree [aurora-silicon/linux](https://github.com/aurora-silicon/linux) is a fork of
`omacom/linux-aurora`. Its profile README says it forked from Asahi over Asahi's AI policy and is not
affiliated with Asahi. It publishes its kernel as **release lanes**, and the `rc` lane is the beta:

| Lane (branch) | Head | Date | vs `omacom/linux-aurora` `integration/aurora` |
|---|---|---|---|
| `aurora-stable` (default) | `b04581b4e67c` | 2026-10-15 | 2 ahead, 639 behind |
| `aurora-rc` (beta) | `2439016d2e8d` | 2026-09-18 | 0 ahead, 2154 behind (stale) |
| `aurora-edge` | `79f87ae69078` | 2026-10-11 | diverged |
| `aurora-wip` (working) | `070c8e4d43a4` | 2026-10-18 09:10 | 1469 ahead, 1521 behind (7.2 rebase line) |

The stable, rc and edge heads are byte-for-byte the SHAs we recorded on 2026-10-16. Only `aurora-wip` moves.
`maralcbr/omarchy-mx-mac` (v4.0.4-mac.1) installs `os-v4.0.4-mac.1.20260924-rc` on both of its channels and keeps
Macs on the Aurora kernel lane, which it reports as qualified on the 14-inch M1 Pro (our model) and the 16-inch M2 Max.
That is where the "beta" (`-rc`) wording comes from.

The same organization also ships repositories outside the kernel. All of them are leads; none is adopted:
[m1n1](https://github.com/aurora-silicon/m1n1) (MIT), [u-boot](https://github.com/aurora-silicon/u-boot),
[aurora-installer](https://github.com/aurora-silicon/aurora-installer) (MIT, forked from asahi-installer),
[speakerguardd](https://github.com/aurora-silicon/speakerguardd) (MIT, a speakersafetyd-compatible daemon),
clones of `asahi-audio` and `alsa-ucm-conf-asahi`, [avd-fw](https://github.com/aurora-silicon/avd-fw) (MIT),
`mesa`, `upower` (based on 1.91.4), `xserver`, `aurora-sep-userspace`, plus Windows and Project Mu work.

**Where it was already documented:**
- `mseries/WATCHLIST.md` (commit `a0d5fb5`, 2026-10-14): watchlist row and the omarchy-mx-mac lead section.
- `mseries/OS9-HANDOFF.md` around line 2058: the omarchy-mx-mac reading.
- `mseries/local-ai/people-watch.json` and `branch-watch.json`: the scheduled watcher covers it.
- `mseries/local-ai/receipts/2026-10-16/m1pro-local-ai-investigation.md`: a table of the stable, rc and edge heads.
- `mseries/aurora-sep/install-aurora-sep.sh`: SEP series `aurora-silicon/linux#69`.
- `mseries/aurora/unified72/series.json` and `branch-audits/2026-10-18-energy.json`: the source of PR #139 is `aurora-silicon/linux`.

**Related, and easy to confuse with it:** the *community tester call* by Chris Kearney (@iconidentify), documented in
`mseries/AURORA-SECOND-BOOT.md` (commit `bfe52e2`, 2026-10-18). Its installer link points at
`iconidentify/aurora-linux` release `sep-7.1.12.aurora2-11.2`. That repository is **archived**, "Frozen at Aurora
2026.10.10.12". Its lineage now lives in `omacom/linux-aurora` and `aurora-silicon/linux`. We did not run it.
`mseries/ICONIDENTIFY-REPOSITORY-REVIEW.md` covers the other iconidentify repositories.

### Aurora Silicon open work that matters to the J314S

| PR | What | Why it matters here |
|---|---|---|
| [linux#316](https://github.com/aurora-silicon/linux/pull/316) + [m1n1#33](https://github.com/aurora-silicon/m1n1/pull/33) | t600x: let `dcpext0` drive the Type-C displays (a device-tree change, +5 lines in `dcp.c`) | **Tested by the author on a J314s.** Two USB-C displays at once (dispext0 and dispext1), and hotplug works. It needs the matching m1n1 change, and old/new DT and m1n1 combinations stay safe. This is the next display step after the primary goal. It is a kernel, DT and m1n1 change, so it belongs to DeepSeek/Codex. |
| [linux#275](https://github.com/aurora-silicon/linux/pull/275) | DCP/tipd USB-C monitor recovery: lost DP link, DPMS wake loop, DCP audio without a sink | May address the 10–15 s re-train cycles seen on `.20` at 04:51 (STATUS-AFTER-20). |
| [linux#302](https://github.com/aurora-silicon/linux/pull/302) | A Type-C port with HPD takes over a pipeline held without it | Hotplug ownership; same area. |
| [linux#296](https://github.com/aurora-silicon/linux/pull/296) | Put an empty CD321x port to sleep, as macOS does | Possible idle-power gain. Not measured. |
| [linux#281](https://github.com/aurora-silicon/linux/pull/281) | AVD: allow more than 32 capture buffers per context | Video decode robustness. |
| `#361` (merged into `aurora-wip` 09:10Z) | `fix/sep-xart-guard-20261018` | SEP xART guard. Relevant to our SEP hang. It is in the #139 line. |

All of these target `aurora-wip`, none is in a release, and none is qualified on this machine.

## 2. Package upgrade survey

"Latest" is as of 2026-10-18 about 10:30 UTC (GitHub API, the Launchpad PPA index, and `apt` lists fetched 03:02 local).

| Component | Our pin | Latest upstream | What changed | Action |
|---|---|---|---|---|
| Aurora release (`mseries/aurora/release.json`) | `aurora-2026.10.17.20`, source `c46d7dcd` | same (no release since `.20`) | — | None. The `.20-enh1` boot trial belongs to Codex. |
| Aurora 7.2.10 draft PR #139 (`unified72/series.json`) | head `582e9ef3` (rev 2) | `ffa615e26` (09:40Z) | 173 commits on top, fast-forward. Mostly J700/J813/T8140 bring-up, bindings and MAINTAINERS. Also `sep: boot Touch ID and Thunderbolt display without command-line switches`, AFKV2 external DPTX, aurora-wake s2idle tests, igb/igc for dock Ethernet. | **Report only.** Re-pinning means re-running the CI build and the 64-fix parity triage. That is a kernel task (DeepSeek/Codex). Still a draft: "hardware qualification in progress". |
| omacom/linux-aurora branches and open PRs | 52 branches / 12 PRs (energy audit 08:58Z) | 52 / 12, **no head changed** | — | None. |
| omacom/m1n1 (`release.json`) | `d05ba17d` | `integration/aurora` = `d05ba17d` | — | None. `aurora-silicon/m1n1` is 208 ahead of it (incl. #33). Kernel/boot owners. |
| Ubuntu Asahi PPA m1n1 / u-boot-asahi (`fetch-asahi-boot-packages.sh`) | `1.5.2-2ubuntu0.1~asahi1` / `2025.10-2-1` | same (PPA `Packages.gz` sha256 `407edbdd…`) | — | None. (The archive has `m1n1 1.5.2-2` and `u-boot-asahi 2025.10-0ubuntu2.1`, not used.) |
| AsahiLinux/linux `fairydust` | `ce9f2eba` | `ce9f2eba` (2026-09-08) | — | None. The lane is effectively superseded by Aurora for the dock. |
| omacom/omarchy-mac-pkgs | docs cite `222f7a8`; imports at `b5e10d3`, `aa747a8`, `99fac5c` (PR heads) | main `ffe5246`, 0 ahead of what OMACOM-IMPROVEMENTS audited. PR #21 / #25 / #6 heads still equal our imported revisions. | — | None. 17 open PRs; see section 3. |
| omacom/omarchy-mac `quattro-upstream` | ref `a76179cd` | same | — | None. |
| omarchy-mac-installer | study only, no pin | `492bf1d` (2026-10-18, CI image job) | CI only | Record a commit when the first import happens. |
| omarchy-m1-video (iconidentify) | reference, bridge 1.3.r11 | main `bc0090a` (2026-09-20) | — | None. The bridge we build is the omacom fork below. |
| omacom/libva-v4l2_request (`install-video-decode.sh`, `build-video-decode`) | `c653eaa6` | default branch `avd-fixes` `4f60c51f` | One merge commit; **zero file differences** from `c653eaa` (verified with compare) | None. A bump would be cosmetic. |
| AVD firmware | `/lib/firmware/apple/avd-fw-v2…v5` (copied from the ALARM side) | AsahiLinux/avd-fw pushed 2026-10-15; aurora-silicon/avd-fw (MIT) | Not diffed | Provisioning gap unchanged (BUILD-NOTES). Not touched. |
| Mesa (system) | Ubuntu `26.0.8-1ubuntu0.3` (installed = candidate) | same in resolute-updates | — | None. The Asahi driver comes from upstream Mesa in Ubuntu. No Asahi/Aurora Mesa package is installed, by design. |
| Private compute Mesa (`local-ai/install.sh`) | `joshuaswarren/mesa-1` `7faf04c0` | `honeykrisp-omarchy` = `7faf04c0` | — | None. |
| omarchy-mlx (`local-ai/install.sh`) | `v0.7.33` / `33630f9c` | latest release `v0.7.33`; main 28 commits ahead | unreleased | None until a release. |
| coreglass (`local-ai/install.sh`) | `25603cbf` + `coreglass-local.patch` | tag **`v0.2.0`** `f03a943c` (2026-10-17), 10 commits | Ledger power-state columns, NOISY row marking, `quiet_set`/`quiet_clear`, `--stack` skips server cells. `remote.py` (our patch) unchanged; `git apply --check` passes on v0.2.0. | **Recommend bump to v0.2.0**, not applied: I could not run its test suite here (the sandbox refused running the fetched code). GitHub shows **no license** for coreglass. We only fetch it at install time; keep it out of images. |
| Tether (`install-tether.sh`) | `0.2.38`, sha256 `eec88920…` | `v0.2.38` (latest) | — | Pin already current. **Fixed stale "v0.2.37" text** in PORT-MAP and WATCHLIST. Messages still blocked: BlueZ is `5.85-4ubuntu0.3` (needs 5.86). |
| Touchegg | 2.0.18 `fc30d316` | 2.0.18 | — | None. |
| elementary panel-network / sound / keyboard | `8685ec8e` (8.0.1) / `8b7991c9` (8.0.3) / `2d086e01` (2.4.2) | same heads / releases | — | None. |
| elementary/os base (UPSTREAM-PINS) | merged to `7024fd04` | main `a6b2376a` (2026-10-14) | One commit, #917: `kmscon` added to `mkosi.images/base/mkosi.conf.d/core.conf` ("Use kmscon for everyone") | **Separate upstream-sync PR, not applied here.** It replaces the VT console in the unbuilt factory image, so it can affect the LUKS-unlock/Plymouth path. Needs a VM smoke check. `kmscon 9.3.2-1` exists for arm64 in resolute. |
| asahi-audio / speakersafetyd / alsa-ucm-conf-asahi (apt) | `3.4-2` / `1.1.2-4` / `8-3` (Ubuntu universe) | upstream asahi-audio `v5.0` (2026-10-02), speakersafetyd `3.0.0` | Major versions newer than Ubuntu | **No action.** It is the owner's running audio stack (AGENTS.md). Track for the factory image only. |
| CodexBar (`install-codexbar.sh`) | `v0.77.0` | `v0.77.0` (2026-10-16) | — | **Reported only**: the pin is current. Another agent owns CodexBar. |
| apt (`apt list --upgradable`, read-only) | — | **0 upgradable** (lists fetched 03:02 local; no holds) | — | Nothing to do. `apt update` was not run. |

## 3. WIP branch inspection

### Upstream WIP

- **omacom/linux-aurora:** unchanged since the 08:58Z energy audit (`aurora/branch-audits/2026-10-18-energy.json`):
  52 branches, 12 open PRs. Only #139 moved (see table).
- **aurora-silicon/linux:** 85 branches, 31 open PRs. Groups: the `apif-*` stack (M5/T6050 under SPTM; DjDeveloperr,
  #238–#257), `aurora/bits/*` (a split patch series), H17P EDID diagnostics (`diag/`, `test/`, `fix/h17p-*`, 2026-10-13),
  J700 (Neo) and J514S/J616S/J613 bring-up, and the M1/M2 display PRs in the section-1 table. The named
  `fix/m1m2-regressions` and `fix/m1m2-typec-usb4-router` branches **no longer exist**. That made our scheduled watcher
  fail on `main` (fixed below).
- **aurora-silicon/m1n1:** 14 branches, 9 PRs, including Ante042 `dcp-enable-typec-routes` (#33),
  `satchlj/sep-alias-copy` and iconidentify `fix/usb4-pcie-adapter-alias`.
- **omacom/omarchy-mac-pkgs (17 open PRs):** our imports (#21 Bluetooth resume recovery, #25 sleep/power report, #6
  keyboard hwdb) still match their heads. Worth a look:
  - #2 "Keep the Apple speaker DSP graph running between streams". It conflicts in spirit with our 30 s sink-suspend
    default; read it before the next audio change.
  - #33 performance governor on AC (draft). This is policy, and needs an A/B on power.
  - #12 Touch ID fingerprint reader naming (draft).
  - #32 mpv on llvmpipe.
  - The boot and limine PRs (#13, #17, #35, #36) are out of scope.

### Our branches (vs `origin/main` `a197695`; conflicts from `git merge-tree`, not a real merge)

| Branch / PR | Ahead | Contents | Merge test | Recommendation |
|---|---|---|---|---|
| `power-usage` / #88 | 8 | Dictation Whisper fallback and stricter threshold; CodexBar native elementary Settings window; handoff note; **`rust/target` build output** | Clean; CI green | Merge **after** the CodexBar agent finishes; `claude/codexbar-claude-switch` and `claude/dictation-finish` sit on the same tip. The owner asked for the rust build output, but it is **34.8 MiB of incremental `target/` artifacts with no Cargo sources on main** (those are on `deb/mseries-plugin-repo`). Confirm the owner still wants it on `main`, or move it to a release asset. |
| `feat/mcp-calendar-browser-mail` / #86 (draft) | 3 | Scoped Calendar/browser/Mail MCP adapters; **watcher fix `7318ecd`** (survive deleted named branches); design doc | Clean; CI green; the watcher passed on this branch | **Merge first**, or cherry-pick `7318ecd`: scheduled "Watch public upstreams" runs on `main` have failed since 2026-10-17. |
| `claude/power-optimization` (no PR) | 1 | Opt-in reversible service/wake trims and an alternating A/B harness (`mseries/power/optimize/`) | Clean | Open a PR. Merge after one real A/B run. |
| `orchard-incus-import` / #73 | 5 | Orchard for Incus: Python/GTK app plus native Vala/Wingpanel app, UX and timeouts | Conflicts only in OS9-HANDOFF.md and ROADMAP.md | Rebase, resolve the doc conflicts, merge. It supersedes the Orchard first cut in #57. |
| `feat/webrtc` / #81 (draft) | 4 | WebRTC screen share, recording and phone input; SER8 activation tools | Doc conflicts only | Keep as a PR. Review against the remote-desktop scope (POS/desktop/support, never healthcare). |
| `deb/mseries-plugin-repo` / #67 | 4 | CI-built plugin debs; rust `mseries-power` scaffold and Cargo.lock; an Omarchy upstream audit doc | Clean | Merge via PR (it brings the rust sources the #88 build output belongs to). |
| `backup/deb-mseries-plugin-repo-local` | 5 | Local copy of #67 plus a battery commit already on main (patch-equivalent) | Doc conflicts | Abandon or delete after #67 lands. |
| `vm-toolkit-desktop-fixes` / #72 | 3 | `mseries-vm` toolkit (Windows UUP, ARM Secure Boot), window corners, natural scroll, quieter chime | Conflicts: validate-mseries.yml, OS9-HANDOFF, enhance.sh, install-gala-screen-corners.sh | Rebase and resolve the code conflicts (corners/enhance changed on main), then merge. |
| `brightness-sub-floor` / #57 | 1 | Sub-5-nit brightness (perceptual ladder, logind write, Gala dim layer) plus the first Orchard cut | Conflicts: docs and install-gala-screen-corners.sh | Rebase **without** the Orchard files (superseded by #73). Display behavior needs the owner's explicit OK before any live test. |
| `claude/airplay-destinations` (no PR) | 7 (2 already on main) | AirPlay output dots/group, Quick Settings sound-output switcher, CodexBar sessions, plus a mixed "WIP checkpoint" (fairydust DP-tunnel RE, orchard, brightness, desktop defaults) | **15 conflicting files**, including install-codexbar.sh, the CodexBar Indicator and the fairydust usb4 docs | Do not merge as is. Cherry-pick `636b239`, `3b8f31c` and `0eeefa7` (AirPlay + sound output) onto a fresh branch from main. Drop the checkpoint: the fairydust DP-tunnel path is superseded by Aurora `.20`, which trains the dock. Leave the CodexBar commits to the CodexBar owner. |
| `feat/omacom-hardware-improvements` | 3 | Merged as PR #80 (all 21 added files are on main) | — | Delete the branch. |
| `codex/aurora-energy-releases` | 0 | Merged (#83–#85) | — | Delete the branch. |
| `codex/aurora-enh1-boot-trial` | 0 | Merged as #87. Active Codex work | — | Do not touch. |

Suggested order: #86 (watcher) → #67 → #88 → #73 → #72 → #57 → #81. AirPlay should go in as a new, split branch.

## 4. What this branch changes

1. `mseries/local-ai/branch-watch.json`:
   - Replaced the two deleted `aurora-silicon/linux` named branches with `aurora-wip`.
   - Added `omacom/linux-aurora` (base `integration/aurora`) and `aurora-silicon/m1n1` (base `omacom/m1n1`
     `integration/aurora`), both with branch and PR discovery.
   - Verification: running `branch-watch.py` against the live API returned **0 errors** and 85 observations; it
     discovered #139's `unified/7.2.10`, the 12 linux-aurora PRs and the 9 m1n1 PRs. `test_assistants` passed (27 tests).
   - On `main` without #86, the scheduled watcher should stop failing on the deleted refs. That is not yet observed on
     a scheduled run.
2. `mseries/PORT-MAP.md` and `mseries/WATCHLIST.md`: corrected the stale Tether "v0.2.37" text. The installer has
   pinned v0.2.38 since `0c444e2`.
3. This survey.

No release or pin bytes changed. Nothing was installed. Not verified: hardware effect of any upstream item
above; coreglass v0.2.0 tests; the kmscon change in a VM.
