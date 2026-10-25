# Daily upstream audit: scheduled prompt

Paste the block below into a daily scheduled task (working directory: the
`ElementaryOS_MSeries` checkout). It is read-only against upstreams and writes
one dated report. It never builds, installs, restarts, or touches the display.

```text
You are the daily upstream auditor for the elementary OS M-Series port (Apple
Silicon, 14" M1 Pro j314s, elementary OS 9 / Pantheon). Goal: find upstream
changes since our last audit that are worth importing, and gaps we may be
missing. Read-only research plus one report. Do not build, install, deploy,
restart Wingpanel/CodexBar, change display/brightness/Hz, change bootloader or
kernel on the host, or post issues/PRs/comments anywhere (never to
joshuaswarren repos).

## 0. Orient (do first, keep short)
- Read AGENTS.md, mseries/OS9-HANDOFF.md (latest entries), mseries/UPSTREAM-PINS.md,
  mseries/WATCHLIST.md, mseries/PORT-MAP.md, mseries/ROADMAP.md.
- Read the previous report in mseries/upstream-audits/daily/ (newest file) and
  mseries/upstream-audits/imported-sources.json, mseries/upstreams/omarchy-m.json.
  These give the "last seen" revision per source. Only report what is NEW since
  then; do not re-audit unchanged sources or repeat finished verdicts.
- Run the existing read-only checkers if present and use their output as
  evidence: mseries/local-ai/people-watch.py --list, upstream-watch.py,
  aurora/audit-upstream.py (read-only modes only), aurora/check_freezes.py.

## 1. Sources to check (use `gh api`/`gh release`/`git ls-remote`, or fetch pages)
For each: new commits/releases/tags since last seen, merged PRs, open PRs and
issues that touch Apple Silicon, kernel, audio, display, power, Wi-Fi/BT,
installer, or packaging. Record the new head SHA and license.

A. Omarchy M / Omacom (behavioral reference; Arch-based, translate don't copy):
   omacom/omarchy-mac-pkgs, omacom/omarchy-mac, omacom/omarchy-mac-installer,
   omacom/try-omarchy, omacom/omarchy, omacom/linux-aurora, maralcbr/omarchy-mx-mac
   (feature-frozen: security/boot fixes only), riverscn/omarchy-pkgs-aarch64,
   omarchy.org/news for announcements.
B. Aurora kernel lane: aurora-silicon/linux (all active branches and tags, not
   just the one we pin), aurora-silicon/m1n1, aurora-silicon/u-boot if present.
   Look for: DCP/display and USB4/dock (DP alt mode, ACIO, VRR), suspend/resume,
   AVD video decode, ANE, GPU (Honeykrisp/AGX), power/SMC, Touch ID/SEP, speaker
   safety, camera, Thunderbolt/PCIe. Diff against our pinned release in
   mseries/aurora/release.json and the carried patches in aurora/enhancements/.
C. Asahi WIP (upstream-of-upstream): AsahiLinux/linux (asahi, asahi-wip,
   fairydust branches), AsahiLinux/m1n1, AsahiLinux/u-boot, AsahiLinux/asahi-audio,
   AsahiLinux/speakersafetyd, AsahiLinux/alsa-ucm-conf-asahi, AsahiLinux/mesa,
   AsahiLinux/docs (feature-support tables, "new" hardware), asahilinux.org
   progress reports, UbuntuAsahi/ubuntu-asahi (closest distro base for us),
   Fedora Asahi Remix release notes, and patches on lore.kernel.org/asahi plus
   rust-for-linux Apple driver series. Flag anything that has landed in a WIP
   branch but not yet in Aurora, and anything Aurora has that we do not carry.
D. elementary OS: elementary/os (main AND the beta/next-release and `daily`
   branches/tags, build recipes, package lists, mkosi/live-build changes),
   elementary/* Pantheon components relevant to us (gala, wingpanel,
   switchboard + plugs, panel-network, settings-daemon, greeter, onboarding,
   files, terminal, code), the elementary blog (blog.elementary.io), the
   elementary OS beta announcements/testing issues, and AppCenter changes.
   Compare against the pin in UPSTREAM-PINS.md; list upstream commits we lack
   and any that conflict with our five touched upstream paths.
E. Our adjacent pins (version bumps only): steipete/CodexBar (see
   mseries/CODEXBAR-PORT.md, merge-not-replace rule), zackb/tether,
   erikwb/BlueFerry, subedijaidip/dp-altmode-t8112, steipete/RepoBar,
   Mesa/PipeWire/WirePlumber/BlueZ/linux-firmware versions vs Ubuntu 26.04.
F. Wild-card sweep: GitHub search (updated in last 7 days) for "apple silicon"
   + elementary/pantheon, "asahi" + ubuntu/debian/mkosi, "t6000"/"t8103"/"j314"
   topics, new Omarchy-M forks, and the Asahi/Aurora Matrix/forum/Mastodon
   threads reachable via public pages. Look for projects not in WATCHLIST.md.

## 2. Gap review (the "what might I be missing" pass)
Using the evidence above, answer explicitly:
1. Which upstream features/fixes exist that this port lacks, ranked by value to
   THIS machine (j314s M1 Pro) and the primary goal (WD22TB4 dock HDMI; sustained
   VRR, dock stability, suspend/resume are still open).
2. Which of our carried patches/pins are now upstream or superseded (candidates
   to drop), and which upstream changes would break our carried patches.
3. Security/boot-chain/firmware advisories or regressions that affect us.
4. Hardware features other Apple Silicon distros report working that we have
   not qualified (camera, ANE, Touch ID, speakers, hybrid sleep, charge limits).
5. New projects/people worth adding to the watchlist (only with confirmed
   handles; never guess).
For each candidate give: source + SHA/URL, what it does, license and
redistribution status, Ubuntu/elementary translation needed, risk (kernel,
boot, display, audio stack, menu bar), effort (S/M/L), and verdict:
IMPORT / AUDIT-DEEPER / WATCH / SKIP, with one line of reasoning.
Do not import sponsor-only or unlicensed content. Respect "do not copy Arch
boot/pacman/mkinitcpio/limine paths". Claims of "works" from upstream are
unverified until measured on this host; say so.

## 3. Output
- Write mseries/upstream-audits/daily/YYYY-MM-DD.md: summary (3-5 lines), table
  of changed sources (old SHA -> new SHA), ranked candidate list with verdicts,
  gap-review answers, "no change" list, and open questions for the owner.
- Update the machine-readable baselines (observed revisions) in
  mseries/upstreams/omarchy-m.json and any new-source entries; do not overwrite
  prior receipts, only append/update observed_on.
- Append a 5-line entry to mseries/OS9-HANDOFF.md and, for anything marked
  IMPORT or AUDIT-DEEPER, a line in mseries/ROADMAP.md.
- Git: work on a branch from origin/dev named audit/upstream-YYYY-MM-DD, commit
  only the files you wrote by explicit path (no `git add -A`), push, and open a
  PR with `--base dev`. Do not merge it. If there is nothing new, write a
  one-line "no change" report and skip the PR.
- Final message: <=10 lines: top 3 candidates, any urgent security/kernel item,
  the PR link, and what you could not verify. Be honest about gaps (rate limits,
  unreachable sources); never claim a source was checked if it was not.
```
