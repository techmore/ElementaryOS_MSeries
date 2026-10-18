# Repo split secret scan: orchard-incus and TM-Remote (2026-10-18)

Purpose: inform the owner's decision on making `techmore/orchard-incus` and
`techmore/TM-Remote` public. Both repositories are still **private**; no
visibility was changed. Secret values are never reproduced here: credential-like
strings are described by file and kind only. Hostnames and IPs are listed
because deciding whether they may be published is the point of the review.

## Scope

Fresh `git clone --mirror` of each repo, scanning every ref (`--all`): all
branches, tags and GitHub `refs/pull/*`.

| Repo | Refs | Commits | Heads at scan |
| --- | --- | --- | --- |
| orchard-incus | main, elementaryos-mseries-import, codex/wingpanel-indicator, pull/1, pull/2 | 13 | main `0fc9800` (merge of PR #2) |
| TM-Remote | main, elementaryos-mseries, dependabot/go_modules/golang.org/x/crypto-0.52.0, pull/1-8, tags v0.1.0, v0.2.0, v0.3.0, v0.3.127 | 78 | main `fb64501`, elementaryos-mseries `132be05` |

## Tools

| Tool | Version | Install | Integrity |
| --- | --- | --- | --- |
| gitleaks | 8.30.1 (linux_arm64) | `~/.local/bin/gitleaks` | sha256 `e4a487ee…b080` matched the release `gitleaks_8.30.1_checksums.txt` |
| trufflehog | 3.97.9 (linux_arm64; picked because it is more than two weeks old, the newest was 10 days old) | `~/.local/bin/trufflehog` | sha256 `372c5686…d705` matched `trufflehog_3.97.9_checksums.txt` (the cosign signature was not checked; cosign is not installed) |
| targeted greps | Python script over the added lines of `git log --all -p`, plus metadata, file-name and blob-size checks | scratchpad only | n/a |

Commands: `gitleaks git <mirror> --log-opts=--all --redact=100`;
`trufflehog git file://<mirror> --bare --no-verification --results=verified,unknown,unverified`
(run offline, so no candidate was sent to any provider for verification).

## Results: scanners

| Repo | gitleaks | trufflehog |
| --- | --- | --- |
| orchard-incus | 0 leaks (~0.93 MB) | 2 unverified `URI` hits: one line in `tests/model-smoke.vala`, found in two commits. Test fixture: a `user:pass@example.test` URL that the test expects `validate_endpoint` to reject. **Test value, not a secret.** |
| TM-Remote | 0 leaks (~3.4 MB) | 0 (1255 chunks) |

## Results: targeted greps

Patterns: PEM private keys and certificates; AWS/GitHub/OpenAI-style/Slack/Google/Tailscale
keys; JWTs; password/secret/token/api-key assignments; APNs/MDM tokens (PushMagic,
UnlockToken, BootstrapToken, `com.apple.mgmt.*` topics); IPv4; e-mail; hostnames; MAC/UDID/serials;
`/Users`/`/home` paths; SSH public keys and fingerprints; sensitive file names
(`.p12 .pem .key .mobileconfig .env .db` and the like); blobs over 300 KB.

### orchard-incus

| Finding | Where | Class |
| --- | --- | --- |
| No private keys, certificates, API keys or tokens | all history | none |
| `secret@example.test`, `example.internal`, `10.40.0.1/24` | tests, ResourceBrowser placeholder | test/example |
| `10.169.229.233` | `python/tests/test_backend.py` | sample Incus bridge address (RFC1918), test data |
| Owner's personal Gmail as commit author/committer | 16 commit-metadata entries (`sdolbec` and `Techmore` identities) | **real personal e-mail** (already public in ElementaryOS_MSeries history) |
| README mentions the live-test host had "Rupert and orchard-test instances" | README.md | internal instance names, harmless |

### TM-Remote

No credentials found. All token, password and PushMagic values sit in `*_test.go`
or `test/` files and are synthetic (`UDID-1`, `SERIAL123`, `11111111-2222-…`
UUIDs, `com.apple.mgmt.External.TEST`, `*-profile-password` PKCS#12 test identities generated at
test time). `turnserver.conf.example`, `environment.example` and the Caddyfile use
`REPLACE_WITH_…` placeholders. The `"Password":` plist field in `mdm_server.go` is
filled from a variable, not a literal. Committed `.pyc` files (`scripts/__pycache__`,
in history only, not on main) hold no absolute user paths. No `.p12/.pem/.key/.mobileconfig` files exist in any commit.

What it does contain is **real infrastructure and personal data**:

| Finding | Where (examples) | Class |
| --- | --- | --- |
| Tailnet name `tailf80972` with node names `techmore-2`, `csp-bfs-mini`, `node` (`*.tailf80972.ts.net`) | docs/COMPLETION-AUDIT.md, docs/MATT-SCREEN-MIRROR.md, docs/REMOTE-DESKTOP-ROADMAP.md, main_test.go, elementaryos-mseries/webrtc/deploy/gateway.py and its test | **real** hostnames |
| Tailscale CGNAT addresses of real nodes (`100.127.99.74`, `100.69.38.89`, `100.82.173.72`, `100.82.173.10`) | README.md, docs/*, scripts/install-control-plane-*.sh, scripts/install-linux-tailnet-routing.sh | **real** (reachable only inside the tailnet) |
| LAN addresses of named machines (`10.20.0.105/106/109/117`, `10.2.0.2`, `192.168.3.251`, `192.168.222.220/244`) | README.md, docs/*, hosts.example.json (also has the username `sdolbec`), scripts/test-screen-mirror.cjs, webrtc gateway.py | **real** internal topology |
| Staff names and workstation details: "Matt" and "Ryan" with SSH user, host ID, IP, OS and installed services | docs/MATT-SCREEN-MIRROR.md, docs/matt-screen-*.service, related docs | **real personal data about third parties** |
| Organisation domains `stoverparc.org` (`mdm.`, `relay.`, `remote.`; also `remote.stoverparc.com`) and `cybersecuritypilot.org` (`daedalus.`, `remote.`) | docs/PUBLIC-CONTROL-PLANE.md, elementaryos-mseries/webrtc/* | **real** hostnames of planned or running services |
| Real Apple TV identifiers (AirPlay `deviceid`, `btaddr`, `gid`, model) captured from a LAN device | discovery_test.go, testdata/appletv_airplay_unicast_response.hex | **real** device identifiers, low sensitivity |
| Two SSH host-key SHA256 fingerprints | docs | real but public by nature, low |
| `/Users/seandolbec` (14 lines), `/home/sdolbec` (9) | docs, scripts | real usernames, low |
| Owner's personal Gmail as committer (7 entries); 134 commits use the placeholder `sean@example.com` | commit metadata | **real personal e-mail** in 7 entries |
| Vendored noVNC author e-mails (`acme.com`, `widget.com`, `jalf.dk`) | web/vendor/novnc | third-party attribution, keep |
| Dependabot reports 18 open alerts on main (8 critical, 3 high, 7 moderate) | GitHub push notice | not a secret; becomes publicly visible as advisories once public |

The WebRTC import (`elementaryos-mseries/`) adds nothing new to this exposure:
its stoverparc hostnames, `techmore-2.tailf80972.ts.net` and `192.168.3.251`
are already public in the public `techmore/ElementaryOS_MSeries` branch
`feat/webrtc`. `discovery-2026-10-17.json` lists branch names and SHAs of ten
techmore repositories, all of which are currently public.

## Verdict

- **orchard-incus: safe to make public.** No secrets, no customer data, test
  fixtures only. The one optional decision is the owner's personal Gmail in commit
  metadata, which is already public through ElementaryOS_MSeries. If it should
  not appear here, rewrite with `git filter-repo --mailmap` before publishing.
  That changes every SHA, including merge `0fc9800`.
- **TM-Remote: no secrets to rotate, but not ready to publish as-is.** Publishing
  would disclose the tailnet name and node names, internal LAN/Tailscale topology,
  staff names with their workstation access details, real device identifiers and
  the owner's personal e-mail. Before making it public:
  1. Remove or anonymise `docs/MATT-SCREEN-MIRROR.md`, `docs/matt-screen-*.service`
     and `docs/SER8-SCREEN-MIRROR.md`/`ser8-*` (or move them to a private ops repo).
  2. Replace real IPs/hostnames in README.md, docs/*, hosts.example.json, main_test.go,
     scripts/* and `elementaryos-mseries/webrtc/` with RFC 5737/6761 placeholders
     (`192.0.2.x`, `100.64.0.x`, `*.example`, `your-tailnet.ts.net`).
  3. Replace the captured Apple TV `deviceid`/`btaddr`/`gid` in discovery_test.go and
     `testdata/appletv_airplay_unicast_response.hex` with synthetic values (regenerate the hex).
  4. Because all of this is in history (and in `refs/pull/*`, which a branch rewrite
     does not change), clean history with `git filter-repo --replace-text`
     (+ `--mailmap` for the Gmail) on a fresh mirror. Then force-push all
     branches and tags, or publish a new repo from the cleaned mirror, since GitHub
     keeps old PR refs. Re-run both scanners and these greps afterwards.
  5. Separately, triage the 18 Dependabot alerts before going public.

If the owner decides the topology/names are acceptable to disclose (the tailnet
addresses are not internet-reachable and several hostnames are already public
via ElementaryOS_MSeries), TM-Remote holds no credentials that would need
rotating. Even then, item 1 (third-party staff details) should be done first.
