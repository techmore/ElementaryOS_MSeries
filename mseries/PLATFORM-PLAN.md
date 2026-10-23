# Platform plan: repo split, the SDK, and the pipeline (proposal, 2026-10-22)

Status: **planning and documentation only. Nothing here is implemented.** Written by Claude at the
owner's request ("document the issue and plan it, then we implement"). Facts below were read from
this repository on 2026-10-22; claims that are the owner's report or my inference are marked
**[owner]** or **[inference]**. Numbers marked *proposed* are targets to argue about, not measurements.

Related: [RUST-IN-THE-STACK.md](RUST-IN-THE-STACK.md), [RUST-UPSTREAM-MAINTENANCE.md](RUST-UPSTREAM-MAINTENANCE.md),
[EDGE-AND-RUST-PLAN.md](EDGE-AND-RUST-PLAN.md), [RELEASE-PIPELINE.md](RELEASE-PIPELINE.md),
[UPDATER-DESIGN.md](UPDATER-DESIGN.md), [KERNEL-FLOW.md](KERNEL-FLOW.md), [BRANCHING.md](BRANCHING.md).

---

## 1. The problem, stated plainly

### 1.1 The headline pain **[owner]**

Building a native app with an agent costs about **12 hours to reach 50 %**. Every new app pays that
price again. The goal: an **SDK a small local model (a Qwen ~4B class) can use to design a whole native
app**, whose output then compiles into our Rust apps, so app work stops being the bottleneck.

### 1.2 What the repository shows today

| Fact (measured on `origin/dev`, 2026-10-22) | Why it matters |
|---|---|
| One repository holds the **kernel/boot tooling** (`mseries/aurora`, `fairydust`, `boot`, `transform`), the **installer**, the **mkosi image**, **Vala patches** for Gala/Wingpanel/Quick Settings, **seven Rust crates**, a **22,125-line Rust compositor**, apps, local-AI tooling (15 MB) and docs | Every task starts with an agent wading through unrelated hardware, installer and docs context |
| `mseries/` has **347 entries**; `OS9-HANDOFF.md` is **10,711 lines (864 KB)**; `ROADMAP.md` is **3,439 lines**. `AGENTS.md` tells agents to read the handoff before starting | A 4B model cannot hold this. Even a frontier agent burns its first hour on orientation **[inference]** |
| History: **2,261 commits**, ~2,000 of them since 2026-10-01; **43 git worktrees** | Extreme churn in one trunk; the "one Git writer at a time" rule serialises everything |
| Each native app is built directly on **gtk4-rs + granite-rs** (`gtk4 0.11` feature `v4_20`, `granite-rs 3.3`) and re-derives its own look, palette, skeleton/empty states, window state, settings window | No shared widget layer. `claude-pantheon-rs` has `look.rs`, `palette.rs`, `skeleton.rs`, `settings.rs`, `winstate.rs`; `mseries-diskspace` has its own `look.rs`, `layout.rs`, `paint.rs`. Same problems solved twice |
| `claude-pantheon-rs/src/app.rs` is **3,426 lines**; `mseries-diskspace/src/app.rs` is 1,234 | Application logic and toolkit wiring are welded together; the unit of change is a giant file |
| The same GTK/Granite pin comment and the `v4_20` workaround is **copy-pasted into four `Cargo.toml` files** | Toolkit quirks live in people's heads and comments, not in a library |
| `claude-pantheon-rs`: 40 commits in ~29 h, with chains of `WIP …` / `Merge branch claude/cpr-47x into claude/cpr-47y` | Agents work in stacked, hand-merged branches; progress is real but the process is fragile |
| UI rules live in a skill (57 lines + references, 309 lines total) and in prose docs | Rules are advisory text. Nothing *rejects* a non-HIG screen mechanically |
| Release pipeline exists but **publishes nothing** (no signing key); compositor and Claude client are **artifact-only**; factory ISO **boot unverified on hardware** | The last mile (an app a user can install and update) is not closed, so every app's "done" is fuzzy |

### 1.3 Root causes **[inference]**, in order of how much I think they cost

1. **The authoring surface is too big and too sharp.** To make a window an agent must handle
   GObject subclassing, `glib::clone!` closures, main-loop/thread rules, `RefCell` plumbing,
   Granite widget feature flags and HIG details. A frontier model gets it wrong repeatedly; a 4B
   model essentially cannot. The number of valid ways to write an app is the problem.
2. **No tight verify loop.** Compile (gtk4-rs is a heavy crate graph) → install → launch → look.
   Each cycle is minutes and, for the model, blind. The tests that exist (`tests/render.rs`) are
   per-app and bespoke. There is no "show me a screenshot and the accessibility tree of what you
   just wrote" command.
3. **Context cost.** Orientation needs the repo, the handoff, the skill and the docs. Small models
   have small windows; large ones still lose time.
4. **Coupling.** Compositor protocol v2, Gala patches, Wingpanel plugins and apps change in the
   same trunk as kernel and installer work, so app PRs wait on or trip over unrelated gates
   (build-status, dev-hygiene, taskbar icon, dock restart).
5. **No definition of "50 %".** We don't have a reference app spec, so progress is measured by
   feel. Without a benchmark we cannot tell whether any change (SDK, repo split, new model) helped.

Point 5 is fixed first (Phase 0): measure before building.

---

## 2. Target shape

### 2.1 Repositories

Today's `ElementaryOS_MSeries` becomes the **integration/distro repo**; four focused repos peel off.
All new repos are created by **history-preserving extraction** (`git filter-repo`), after a
secret scan (the 2026-10-18 scan in [REPO-SPLIT-SECRET-SCAN-2026-10-18.md](REPO-SPLIT-SECRET-SCAN-2026-10-18.md)
is the template). **Originals are never deleted or archived.**

| Repo (proposed name) | Contains | Today it lives in | Owner / pace |
|---|---|---|---|
| `mseries-sdk` | Runtime crate(s), component library, schema, `msdk` CLI, templates, examples, the model benchmark | does not exist yet; seeded from `rust/claude-pantheon-rs`, `rust/mseries-diskspace`, `rust/mseries-updates`, `rust/granite-smoke`, `UI specialist` skill | Highest value, fastest cadence |
| `mseries-wm` | The Smithay compositor (Pantheon shell protocol v2, gestures, popups, Xwayland), its protocol XML, conformance tests | `rust/pantheon-compositor` (22 k lines, 131 commits), `mseries/pantheon-rust-compositor/`, `window-snapping/` | Frontier work; replaces Gala only in qualified slices |
| `mseries-display` | Userspace display stack: KMS/atomic helpers, EDID, hotplug, link-status/flip-retry, display-config daemon, dock qualification receipts. Compositor-agnostic crates that `mseries-wm` depends on | pieces now inside the compositor (`edid.rs`, `kms_props.rs`, `link_status.rs`, `flip_retry.rs`, `hotplug.rs`, `display_config.rs`, `display_trace.rs`) plus `check-display-paths.sh`, dock docs | Carries the **PRIMARY GOAL** (dock HDMI picture); evidence-gated |
| `mseries-kernel` | Aurora/Fairydust patch series and pins, kernel config checks, `qualification.py`, boot-trial tooling, hardware-test receipts, m1n1/U-Boot pins | `mseries/aurora`, `mseries/fairydust`, `mseries/boot`, `mseries/aurora-sep`, `mseries/aurora-touchid` | Owned by the kernel lane (DeepSeek); slow, hardware-gated |
| `ElementaryOS_MSeries` (stays) | Installer (`bin/`, `transform/`), mkosi image, Vala patches for upstream Pantheon, apt/release pipeline, website, docs index, the **pin manifest** tying the other repos' revisions together | everything else | Integration only; no feature code |

Why this split and not "one repo per crate": the unit of ownership is a *change cadence and a
verification gate*, not a crate. Kernel changes are gated on a reboot of the owner's machine; the
compositor on on-device acceptance; the SDK on a benchmark that runs in minutes. They should not
share a queue.

Dependency direction (no cycles):

```
mseries-kernel ─┐
                ├─► ElementaryOS_MSeries (image, installer, apt) ◄─ mseries-sdk apps
mseries-display ─► mseries-wm ─┘                                     (apps depend only on mseries-sdk)
```

Apps built with the SDK **do not live in the SDK repo**; they get their own small repos or an
`apps/` monorepo (decision in §7). The SDK repo holds only the toolkit and its examples.

### 2.2 The pin manifest (the glue)

One machine-readable file in the integration repo, `mseries/pins.toml`, extends
[UPSTREAM-PINS.md](UPSTREAM-PINS.md): per repo, the commit that the current image is built from,
plus the upstream pins (Gala, mutter, Smithay, granite-rs). CI in the integration repo builds only
from the manifest, so a repo split cannot silently change what ships. Bumping a pin is a PR that
cites the receipt (test run, hardware note) proving it.

### 2.3 What deliberately does *not* move

- Vala patches for Gala/Wingpanel/Dock must keep applying to upstream; they stay beside the image
  (see [RUST-UPSTREAM-MAINTENANCE.md](RUST-UPSTREAM-MAINTENANCE.md): "stay on upstream Vala").
- Installer shell and `transform/` stay; rewriting them adds risk, not safety.
- The Asahi/Arch boot-host arrangement ([KERNEL-FLOW.md](KERNEL-FLOW.md)) is unchanged. The kernel
  repo only changes where its sources and receipts live.

---

## 3. The SDK: design for a small model

### 3.1 The thesis

A small model does well when the **space of valid programs is tiny, regular and checkable**, and
badly when it must know a large toolkit's idioms. So we don't hand it GTK. We hand it a **closed
vocabulary**, and we make every mistake produce a one-line, fixable error within seconds.
The "beautiful Rust output" is produced by our runtime, which we write once, carefully, with a
frontier model and review; the small model only describes *what* the app is.

### 3.2 Shape of an SDK app

An app is **three small things**, none of which touches GObject, closures or threads:

```
app.toml        identity: id, name, icon, category, permissions/capabilities it needs
ui.msdk         the view: a declarative tree of components bound to state (closed vocabulary, schema'd)
logic.rs        State, Msg, update(state, msg) -> Cmd   (plain Rust; Elm-style; no UI types)
```

- **View** = declarative and *validated against a schema* before anything compiles.
  Roughly 30 components at first: Window, HeaderBar, SourceList/Sidebar, List, Row, Card, Text,
  Entry, Search, Button, Switch, Dropdown, Tabs, Grid, Dialog, Toast, EmptyState, Skeleton,
  Progress, Chart (bar/line/treemap), Markdown, Terminal, WebView. Each has fixed properties and
  built-in HIG behaviour (spacing, focus, keyboard, accessibility, dark mode, text zoom, HiDPI).
- **Logic** = `State`, `Msg`, `update`, with side effects returned as **`Cmd` values** (run process,
  HTTP/WebSocket request, read/write SQLite, timer, notify, open portal file chooser, D-Bus call).
  The runtime executes them off the main loop and sends results back as `Msg`. Concurrency is the
  runtime's problem.
- **Capabilities** are declared in `app.toml` and are the only way to reach the system (network,
  filesystem scope, D-Bus names, keyring, notifications, camera/mic/portal). This doubles as the
  permission manifest and keeps generated code reviewable.
- **Two execution modes from the same source:**
  1. **Dev/interpret:** `msdk run` loads `ui.msdk` + compiled logic and **live-reloads the view on
     save** with no recompile of the toolkit (target: edit→pixels in ~1 s, *proposed*).
  2. **Release/compile:** `msdk build` generates Rust against `gtk4-rs`/`granite-rs` (the
     "modern beautiful Rust"), strips the interpreter, emits a static binary and a `.deb`.
  Keeping both modes means a model gets a fast loop while users get a native, lean binary. The
  generated Rust must be readable; it is a deliverable, not an intermediate.

### 3.3 The loop that makes a 4B model viable

| Command | Purpose | Why a small model needs it |
|---|---|---|
| `msdk new <template>` | Scaffold from a known-good template (list, detail, settings, dashboard, chat, form) | Starts from working code, not a blank page |
| `msdk check` | Schema + lint + HIG rules (missing labels, bad nesting, tap target, no focus order, hard-coded colours) | Errors are one line each with a suggested fix. Rejects invalid output before compiling |
| `msdk shot` | Headless render of every screen/state to PNG **plus** an accessibility-tree JSON | The model (or a VLM/judge) can *see and read* what it built |
| `msdk test` | Run `update` against scripted `Msg` sequences, assert on state and tree | Logic tested without a display |
| `msdk build` / `pack` | Generate Rust, compile, build `.deb` with `.desktop`, metainfo, icon, **dock-tracking and WM_CLASS correct by construction** | Removes the "new app shows the wrong icon" class of bugs ([DOCK-APP-TRACKING.md](DOCK-APP-TRACKING.md)) |
| `msdk bench` | Run the benchmark suite (§3.5) against a given model | Tells us if any change helped |

**Constrained generation:** publish a JSON Schema and a GBNF grammar for `ui.msdk` and `app.toml`,
so llama.cpp-class runners can *only* emit valid trees. The Rust part is kept small enough that a
fill-in-the-blank template (`update` match arms) is enough for most apps.

**Error budget:** `msdk check` runs in under a second and every diagnostic is a single line
(`ui.msdk:14 Row has no label; add label="…"`). Compile errors from the Rust side are rewritten
the same way where we can.

### 3.4 Build vs adopt **[decision needed]**

Existing Rust UI stacks already solve parts of this:

| Option | For | Against |
|---|---|---|
| **Relm4** (Elm-style on gtk4-rs) | Same toolkit we ship, same model as §3.2, mature | No closed vocabulary, no schema, still exposes GTK to the author; Granite integration is ours to add |
| **Slint / iced** | Declarative, fast iteration | Not GTK/Granite: loses elementary theming, portals, Wingpanel/dock behaviour unless re-implemented |
| **Own runtime on gtk4-rs + granite-rs** | Full control of vocabulary, HIG, a11y, generated code | Most work up front |

Recommendation: **spike Relm4 as the execution backend** behind our own schema and `msdk` CLI, so
we own the vocabulary (the part that matters for small models) without writing a widget runtime
from nothing. If the spike shows Relm4 leaks too much GTK, fall back to a thin runtime of our own.
The schema, CLI and benchmark are valuable either way; the backend is swappable by design.

### 3.5 Proving it: the benchmark

Without this, the SDK is a hope. `msdk bench` runs a fixed list of **app specs** (one paragraph
each) against a model and records, per spec:

- produced valid `ui.msdk`/`app.toml` first try (y/n); retries to valid
- `msdk check` clean; `msdk test` pass; builds
- screenshot judged against a rubric (VLM or human, same rubric each time)
- wall-clock, tokens, and number of tool calls

**Seed corpus = the apps we already built**, re-expressed as specs and ported by a frontier model
once: Disk Space (`mseries-diskspace`), Software Updates (`mseries-updates`), a settings pane
(Work Mode / Display), a dashboard (CodexBar-style usage), a list/detail viewer, and a chat client
(`claude-pantheon-rs`). Their current implementations are the golden outputs and the
"before" numbers.

*Proposed* acceptance targets (adjust after the first baseline):
a 4B model produces a **valid, checking, building** app for a simple spec in **< 10 minutes
wall-clock, ≥ 70 % of first attempts**; a frontier agent reaches "50 %" of a real app in
**< 1 hour** instead of ~12.

### 3.6 Dogfooding is the long game

Once the vocabulary is stable, rebuild shell surfaces on it: Wingpanel indicators, Quick Settings
tiles, Switchboard-style settings pages, the Updates app. Fewer hand-written Vala patches against
moving upstream; every surface automatically themed, accessible and consistent. This is the
payoff that turns the SDK from "app toy" into "the platform".

---

## 4. The pipeline, today and after

### 4.1 Today (read from the repo)

```
upstream (elementary/os, Gala, Asahi linux, m1n1, Mesa, omarchy-mac)
   │  watchers: upstream-watch.py, touchid-watch.py, people-watch.py
   ▼
UPSTREAM-PINS.md (prose) ──► hand-run install scripts / mkosi image ──► factory ISO (builds, boots in VM; hardware unverified)
   │
   ├─► kernel: Arch side pacman → hook copies modules into @elementary   (owner's machine only)
   ├─► debs: mseries-debs.yml → dev / stable apt suites   (NOT PUBLISHED: signing key missing)
   └─► Rust apps/compositor: CI artifacts only, no installed-and-launched check
```

Gaps: pins are prose, not data; nothing gets to a user through apt yet; Rust apps/compositor stop
at "artifact"; app "done" has no shared definition; the kernel→display→compositor chain is tested
by hand on one machine.

### 4.2 After

```
per-repo CI (own gate, own cadence)
  mseries-sdk     : check + unit + render snapshot + model benchmark (minutes)
  mseries-wm      : build + nested-compositor conformance + popup/freed-surface acceptance
  mseries-display : build + EDID/KMS replay tests; hardware receipts attached to PRs
  mseries-kernel  : config check + boot-trial receipt; promoted only by owner
        │ each publishes a signed, versioned artifact + a receipt
        ▼
integration repo: pins.toml bump PR ─► image + debs ─► QEMU smoke ─► installed-and-launched check ─► dev suite ─► (release PR) ─► stable suite
        ▼
mseries-update (already designed) on the user's machine
```

SDK-built apps get this for free: `msdk pack` output drops into the same `dev` suite with a
generated installed-and-launched check, which is the missing gate that keeps the compositor and the
Claude client artifact-only today.

### 4.3 Blockers to unblock regardless of the split

1. Create the signing key ([release/KEY-RUNBOOK.md](release/KEY-RUNBOOK.md)) and pick the apt host
   (the Pages-source conflict in [RELEASE-PIPELINE.md](RELEASE-PIPELINE.md)); until then nothing ships.
2. Add an installed-and-launched smoke test generic enough to cover any app.

---

## 5. Keeping agents (and small models) un-lost

Part of the "12 hours" is orientation. Concrete rules for every new repo and, over time, this one:

- `AGENTS.md` ≤ ~60 lines, **no** instruction to read a giant ledger first. It links to a
  `docs/INDEX.md` and a `CURRENT.md` of ≤ 100 lines (state, next task, blockers).
- Handoffs are **append-then-rotate**: `OS9-HANDOFF.md` (10.7 k lines) is archived per month and
  replaced by a short current file. History is kept, not deleted.
- One-page `CONTEXT.md` per repo for a small model: what this repo is, the 10 commands, the 5 rules.
- Rules that can be mechanical **become lints** (`msdk check`, CI), not prose in a skill.
- Generated indexes (docs, pins, branches, worktrees) instead of hand-edited tables.
- Worktree hygiene is automated (extend [DEV-HYGIENE.md](DEV-HYGIENE.md)); 43 live worktrees is a cost.

---

## 6. Phases, exit criteria, order

Order is by **value ÷ entanglement**: SDK first (biggest payoff, least coupled), kernel last
(most fragile, already effectively separate).

| Phase | Work | Exit criterion |
|---|---|---|
| **0 Baseline** (days) | Write 6 app specs; record how long the current process takes on two of them (clock time, tokens, retries); define the rubric | A table of "before" numbers committed to the repo |
| **1 SDK spike** (1–2 wk) | Relm4-vs-own-runtime spike; `ui.msdk` schema v0; `msdk check` + `msdk shot`; re-express Disk Space as an SDK app | Disk Space rebuilt from ≤ 300 lines of `ui.msdk` + `logic.rs`, screenshot matches golden, `check` clean |
| **2 Small-model trial** (1 wk) | Run Qwen ~4B on the 6 specs with constrained generation; iterate the *vocabulary and error messages*, not the model | Benchmark published; first-try validity measured; gap list |
| **3 Extract `mseries-sdk`** | History-preserving extraction, CI, examples, `msdk pack` into the dev suite | Another app (Updates) ships via `msdk pack` |
| **4 Extract `mseries-wm`, then `mseries-display`** | Move crates, add conformance and receipts, switch the integration repo to `pins.toml` | Image builds from pins; compositor acceptance test runs in its own CI |
| **5 Extract `mseries-kernel`** | Move aurora/fairydust/boot tooling and receipts | Boot-trial tooling runs from the new repo; originals untouched |
| **6 Dogfood** | Rebuild Updates, Disk Space, one settings page and one indicator on the SDK | Fewer bespoke GTK files in the integration repo; Vala patches count down |

Each phase ends with a written receipt (what ran, numbers, what failed) in the relevant repo. No
phase starts a hardware change; the owner's bootloader, kernel and running audio stack stay off-limits
per [AGENTS.md](../AGENTS.md).

---

## 7. Decisions for the owner

1. **Repo count and names.** Four new repos as in §2.1, or fewer (e.g. fold `mseries-display` into
   `mseries-kernel` until the display work stabilises)? My lean: four, because the dock goal runs on
   its own evidence gate, but `mseries-display` can wait until after the SDK.
2. **Where SDK apps live.** One `mseries-apps` monorepo, or one repo per app? Lean: one `apps/`
   monorepo while there are < 10 apps, with a rule that apps import only `mseries-sdk`.
3. **Backend spike.** Approve a time-boxed (≤ 1 week) Relm4 spike before committing to own-runtime.
4. **Which small model and runner** is the benchmark target (Qwen3.5-4B via llama.cpp? on SER8 or the
   laptop?). Per past guidance, model runs go on SER8, not the laptop.
5. **Naming.** `msdk`/`mseries-sdk` are placeholders; "MSDK" will also read oddly outside the repo.
6. **Cut-over rule for extracted code.** Mine: copy-then-point (the integration repo consumes the new
   repo via `pins.toml`), originals stay until a release has passed, per the "keep the old script
   until a release has passed" rule already in [EDGE-AND-RUST-PLAN.md](EDGE-AND-RUST-PLAN.md).

## 8. Risks

| Risk | Mitigation |
|---|---|
| The closed vocabulary is too small and apps need escape hatches | Allow a typed `Custom` component backed by Rust, flagged by `msdk check`; track how often it is used as a vocabulary-gap metric |
| The 4B model still fails even with grammars | The benchmark tells us early (Phase 2). Fallback: 4B for `ui.msdk`, a stronger model for `logic.rs`; the SDK still cuts the frontier-agent hours |
| Cross-repo changes (protocol v2 ↔ Gala patch ↔ apps) get slower | `pins.toml` + one integration PR; keep the protocol XML in `mseries-wm` with a conformance suite |
| Split loses history or leaks a secret | `git filter-repo` from a mirror, secret scan before push, originals untouched |
| Scope creep into a new toolkit | The runtime stays a thin layer over GTK4/Granite; Phase 6 is optional |
| Doc rot returns | Mechanical lints, generated indexes, rotation rule (§5) |
