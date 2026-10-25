# Supplemental subscription reports for native T3 — October 25, 2026

Reviewed [joshuaswarren/omarchy-agent-usage-more](https://github.com/joshuaswarren/omarchy-agent-usage-more)
at `734109c8ec947d8f13e2fdc7c66c8e1b25f6ac88` (MIT, Joshua Warren 2026).
The upstream fixture suite passes all ten test groups on this macOS host.
No provider account, credentials, broker or live API was accessed during review.

## Outcome and boundary

The native T3 Usage page continues to show its server's token history, costs and
plan windows. Below that, Local subscription reports reads existing JSON files
on this computer. Usage also opens while disconnected so those reports remain
available. Read reports refreshes files only; it does not run collectors, install
providers, contact APIs or import credentials. New UI follows the existing
Rust GTK4/Granite Usage surface. The app currently lacks gettext infrastructure;
this feature does not establish localization or owner acceptance.

Upstream has sixteen collectors: eight direct API/session sources (ClinePass,
Kimi, MiniMax, OpenRouter, Warp, Kilo, Amp, Factory) and eight omp-broker sources
(Claude Max, Codex, Google AI Pro, Cursor, OpenCode Go, Alibaba, Devin, Ollama
Cloud). They are optional external sources, not sixteen newly installed T3
providers. The QML/plugin service and systemd timer are not ported or enabled.

Existing collectors publish schemaVersion 1 records under
`$XDG_STATE_HOME/omarchy/agents/usage`, normally
`~/.local/state/omarchy/agents/usage`. `src/quota.rs` reads bounded regular JSON
files (64 directory entries, 1 MiB per file, 64 windows per record). It rejects
unsupported versions, missing required fields, nonfinite/out-of-range quota
fractions and malformed/future update times. A fraction of .25 renders 25%.
Failed records do not render their windows. Last-known reports and files older
than fifteen minutes are marked stale. `updatedAt` is a collector record update
time, not proof of a current provider measurement; the UI labels it accordingly.

Accounts/windows are preserved as published, never merged or summed. A reader
cannot recover account identity that an upstream collector already discarded.
In particular, upstream's `limits_for` independently takes the lowest usage for
each named window across accounts. A fixture with A at session10%/weekly100%
and B at session100%/weekly10% yields a synthetic session10%/weekly10% result.
Use upstream's per-account mode when collecting interchangeable accounts too;
do not feed merged records into provider rotation. Claude and Codex collectors
at this revision already use `scan_per_account`.

Supplemental records never alter T3 `Provider`, its server RPC contract,
`pick_provider`, the existing status feed or CodexBar configuration. A remote
T3 environment's quota must be obtained from that environment's service, not
silently inferred from this computer's files. Balances remain distinct from
estimated API-equivalent token costs.

## Findings to preserve during future collection work

- Factory is opt-in upstream because refreshing its WorkOS token competes with
  Droid's CLI session. Do not enable or copy that authentication flow by default.
- The broker config supports shell-command indirection. This app does not read
  that config or execute those commands. The broker's credential snapshot may
  carry token material; do not copy it into UI/status data.
- Upstream's failed-value fraction helper can turn invalid amounts into 0%;
  unavailable is not unused. Nonfinite timestamp inputs also raise exceptions
  in its helper (isolated repro). These errors must remain explicit in a port.
- Broker history fallback carries a prose last-known marker but record update
  time is regenerated. A future versioned service should carry source-observed
  time, account identity and typed stale/partial/error states explicitly.
- The broker is `omp auth-broker`; its existence does not establish the identity
  or API of the owner's separately mentioned Omi service.

## Source boundary and verification

The new Rust reader/presentation is original project code based on the public
record contract; no collector implementation is vendored. Preserve upstream's
MIT copyright and permission notice if substantial code/fixtures are imported
later. Source inspection and upstream fixtures do not establish live provider
endpoint compatibility.

Four focused production-model tests and strict Clippy pass in a GTK-free local
harness. Linux CI runs the full client and isolated feature render gates for
offline opening, multiple accounts, fraction units, stale, failed and malformed
reports. Review final PR CI and render artifacts before claiming a visual pass.
No target elementary installation, live service/account or owner acceptance was
performed on this macOS session.
