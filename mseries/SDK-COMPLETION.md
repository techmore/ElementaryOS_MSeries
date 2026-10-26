# SDK completion and qualification ledger

The requested outcome is a complete, tested and validated Rust Pantheon app SDK.
The product contracts are issue #535, the current APP-BUILDING-GUIDE and
RUST-PANTHEON-SDK, the sdk-bench specs/rubric, and the Dock standard proposed in
PR #605. Existing Signal/Messages deferral remains in force: use synthetic
messaging data for SDK checks; do not resume or replace those clients.

A green compiler/test run is scoped evidence. SDK completion requires every
applicable row below to have retained source-matched evidence; missing evidence
is an open gate. No completion percentage is assigned.

| Requirement | Authoritative evidence needed | Current state / next work |
| --- | --- | --- |
| Ownership/runtime/API support | Published graphics, shell, toolkit and app API versions/owners; stable/provisional/unsupported boundaries; compatibility and deprecation policy | SDK-COMPATIBILITY.md publishes candidate version/owner/migration boundaries and actual host evidence; manifest loading is versioned and atomic; exact real backend OS protocols and release/physical supported-host qualification remain open |
| Description authoring/discovery | Checker, schema, discovery and rules agree; all six starters pass; valid user strings survive generation | Starter escaping repaired; core suite includes current T3 identity/page assertions |
| Typed Rust and standalone app | `msdk gen` emits compiling records/State/Message plus a real GTK executable; original description/rules retained; custom backends explicit | All six model variants compile; actual generated settings app builds/tests/lints and runs on isolated Ubuntu 26.04 x86_64; source-matched receipts in sdk-tests/receipts/2026-10-26; arm64 developer-path run 40363235712 passed on ed9bc5b; current runtime/reference source passes isolated x86_64 checks; current ARM run still needed |
| Clean developer path | Clean checkout to useful app, recoverable service error, typed diagnostic/source context, optional capability, build/package/run guide; coding <=30 min and provisioning/wall time separately measured | Home Storage read-only sample and SDK-GOLDEN-PATH.md added; actual same-process keyboard/AT-SPI failure/retry, eight native reviewed captures, generated app build/lint and package lifecycle pass; measured novice/model trial still needed |
| Services and errors | Version mismatch/unavailable/denied/malformed data through actual adapters; bounded async/cancel/retry behavior; privacy-safe structured diagnostics | Candidate typed async replies, extension ABI checks, safe diagnostics, owned process groups and bounded Rust streaming/partial output implemented; core streaming/context passes macOS and Linux checks; native typed error/recovery/fixture/close checks pass on exact source; backend OS protocols and streaming/app-specific GTK adapters remain open |
| Optional lifecycle | Disabled/closed causes no extra reads, stale completions ignored, sources released; exact scope/account remains visible | Host/window watcher ownership and process cancellation implemented; prior private native D-Bus lifecycle tests pass; RequestContext/Scoped delivery and scoped process cancellation pass macOS/Linux core tests, and exact-source native lifecycle/runtime passes; GTK/streaming/T3 context adapters remain open |
| Native toolkit/UI | Source-matched light/dark, regular/compact, default/larger text and supported scales; keyboard-only primary journey and live accessible names/roles | Generated settings app passes live keyboard/AT-SPI controls; settings and Home Storage compact/regular, light/dark, asserted 10/15-point matrices visually reviewed and retained; target Pantheon/physical scales/owner acceptance remain open |
| Shell/status module | Discoverable reusable CodexBar-derived provider/account module; Windows bottom-right and elementary status hosts; all semantics and exact interaction gates from #605 | Native T3 integration is separate from reusable SDK capability; no parity claim |
| Installation/distribution | Correct executable/desktop ID/icon/metainfo; package validation, fresh install/reinstall/remove and source-installed-loaded identity | `msdk pack` implemented with actual ELF architecture/native-library dependency resolution and validated desktop/AppStream/icon/license assets; isolated x86_64 settings and current Home Storage package/install/reinstall/installed launch/binary equality/remove pass on source-matched snapshots; exact SDK/generated source fingerprints and binary/package hashes retained; arm64/target-distro/target-host qualification pending |
| Reference consumers | T3 monitoring/GitHub actions through actual SDK adapters; comparable native/SDK semantics; read-only authority and account freshness | T3 core fixtures exist; full reference/host/real-account qualification open; Messages remains deferred |
| Performance | Same hardware/workload startup/RSS/idle CPU/wakeups/render metrics; explicit build/provision/queue timings | No new performance result claimed |
| Model usability | Exact licensed model/runtime/weights/prompt/spec; clean isolated no-network trials, same rubric, failures/repairs/interventions retained; independent visual/behavior acceptance | Six fixed benchmark specs exist; controlled repeated runs and baseline comparisons remain open |
| Release/API readiness | All above gates audited against final immutable artifacts, docs match shipped behavior, unsupported scope explicitly recorded | SDK v1 completion remains unproven |

## Current verification environment

This chat's Mac has Rust but no GTK development package. Core checks use an
isolated copy of msdk and its external fixture files to avoid resolving the
unrelated pinned Smithay Git dependency in the whole-OS workspace. Generated
model compilation uses cached Cargo dependencies. This is not Linux GTK, target
Pantheon, installation, hardware or owner visual acceptance evidence.

`mseries/sdk-tests/prepare.py NEW_DIRECTORY` creates the reproducible SDK-only
workspace, keeping the checked-in dependency lock as its starting point. The
M-series SDK developer path workflow provisions Linux separately, tests/lints
core, builds/tests/lints a generated GTK app and captures its actual executable
in light/dark isolated desktops. Its resulting locks/source/hash/screenshots are
retained. Runtime and target-host gates remain open until those are exercised.
