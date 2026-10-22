# Rust Pantheon SDK, Software Updates and System Monitor — 2026-10-22

The shared Rust GTK 4 / Granite SDK remains in the current repository while
its app set and the proposed Kernel, OS and Apps repositories are proven. The
rollout includes T3, Messages, Disk Space, Software Updates, private
Torrential, and the System Monitor preview. The updater is an OS-owned service
with a typed versioned app contract; the UI and shared client adapters belong
to the Apps SDK. App releases may version independently after native
acceptance, and the hub records artifact checksums, SDK/API compatibility and
qualification receipts. Do not create satellite repositories or move source
until their builds, packages and hub integration have passed.

System Monitor currently samples host CPU and memory through SDK polling and
embeds btop via VTE. The custom compositor still needs a versioned read-only
metrics API before compositor counters can appear there. The provisional Mac
window/display radius has not been matched to the physical panel; owner visual
qualification remains open. See [Rust Pantheon SDK](RUST-PANTHEON-SDK.md) and
[Repository Topology](REPOSITORY-TOPOLOGY.md).

## T3 follows the active Pantheon theme — 2026-10-22

T3 visual replies now resolve their light/dark surface, foreground and accent
from the active GTK theme when a WebView is opened. Unstyled page text uses the
system UI font. The unread activity dot uses the existing GTK `@accent_color`
style instead of a fixed blue. Provider identity dots retain their own colors.
Theme lookup adds no polling and is paid only when opening a visual reply.

`cargo fmt --check --manifest-path rust/Cargo.toml -p claude-pantheon-rs`,
`cargo check --locked --manifest-path rust/Cargo.toml -p claude-pantheon-rs`, and
`git diff --check` pass. No tests or GUI theme interaction were run. Visual
checks in both Pantheon light and dark modes remain open; GTK 4.10 deprecated
named-color lookup without a replacement, so that lookup is narrowly scoped
and will need revisiting if the app moves to GTK 5.

## Rust Messages responsive layout and actionable errors — 2026-10-22

The shared SDK now reevaluates responsive classes after mapping and on native
surface layout events, and recomputes text-based breakpoints after font/DPI
changes. Rust Messages uses that watcher for compact/regular navigation. Shared
CSS uses supported, direction-aware GTK margins; avatar widgets clip images in
GTK rather than using unsupported CSS overflow. Missing BlueFerry D-Bus service
errors now show a retry hint while retaining raw diagnostics in a tooltip.

Formatting, 16 Messages/SDK tests, strict Clippy and the Messages build pass.
A private no-service Xvfb run verified initial mapped layout and clean GTK CSS;
live resizing was not qualified because the isolated X server had no window
manager to deliver normal compositor resize events. Owner visual, accessibility,
phone-send and screenshot-drop acceptance remain open.

## Rust Messages per-phone pin scope and shared keyring — 2026-10-22

Rust Messages now validates bounded Apple pin snapshots, reviews conversation
matches, orders the sidebar from the imported snapshot and stores choices in
Secret Service under BlueFerry's optional stable phone UUID. Before saving, it
checks that the same phone is still selected. The legacy Python GTK client now
reads the same UUID and generic Secret Service item, migrating its old
custom-schema/MAC-hash item locally once a valid UUID is available. Missing or
changed phone IDs clear the old view state, and stale asynchronous pin loads are
ignored. A direct jump to Rust before the Python migration can require
re-importing the snapshot.

BlueFerry [PR #277](https://github.com/erikwb/blueferry/pull/277) is open and
adds the optional UUID without changing Messages API v2. Its branch has no
reported checks yet. Until that change is merged and released, older status
replies omit the UUID and import actions explain that BlueFerry must be updated.
Code commit `b3ed900b` is on [PR #526](https://github.com/techmore/ElementaryOS_MSeries/pull/526).
Its current-head checks pass: Rust Messages formatting/lint, ARM64 build and
package, desktop metadata, SDK/System Monitor, Software Updates, Disk Space,
native pin import/keyring, Apple pin readers, M-series wiring and plugin
packages. An earlier commit failed strict Clippy; `b3ed900b` fixes those three
findings. Local formatting, compile, strict Clippy, Python syntax compilation
and `git diff --check` also pass. No local test suite or GUI was run. Live
keyring/UI behavior and owner-phone acceptance remain open. The PR stays draft.

## Rust Messages local timestamp parity — 2026-10-22

The shared SDK now formats BlueFerry ISO timestamps in the local timezone with
stable calendar labels (Today, Yesterday, weekday, or date plus year) and a
12-hour clock, matching the qualified Python client's behavior. Invalid values
fall back to a short, single-line label. The Rust Messages conversation list
uses compact local labels, and the message timeline uses centered local
date/time headings instead of raw ISO strings.

**Source/build validation:** `cargo fmt --manifest-path rust/Cargo.toml
--package mseries-pantheon-kit --package mseries-messages`, `cargo check
--locked --manifest-path rust/Cargo.toml -p mseries-messages`, and `git diff
--check` passed. No test suite or live UI render was run for this change. Next:
verify same-day, previous-day and older-date labels on the owner session,
including timestamps near a local timezone boundary.

## Rust Messages body search parity — 2026-10-22

The Rust conversation search now matches loaded message bodies as well as
conversation names, recipients and the latest preview, matching the existing
Python client. GLib Unicode case folding handles text consistently; the filter
index is rebuilt when BlueFerry refreshes the bounded snapshot, rather than
normalizing every message again on each keystroke. Local-only conversations
refresh the index after a successful send. The index is shared across cloned
conversation models to avoid copying history text while rebuilding the list.
Search does not request more history or log query text.

**Source/build validation:** `cargo fmt --check --manifest-path rust/Cargo.toml
--package mseries-messages`, `cargo check --locked --manifest-path
rust/Cargo.toml -p mseries-messages`, strict Clippy with warnings denied, and
`git diff --check` passed. No test suite or GUI interaction was run for this
change. Next: verify search navigation and clearing on the owner session.

## Rust Messages conversation grouping — 2026-10-22

The shared Rust Pantheon SDK now turns message timestamps into timeline
presentation hints: messages within five minutes group by direction and, for
groups, sender; a centered local date/time heading appears at the start of a
day or after a 30-minute gap. Group messages show the sender once per run.
Unparseable timestamps stay isolated and use the SDK's safe one-line caption.
The Rust view uses these hints to tighten spacing between grouped bubbles,
bringing it closer to the current Python Messages client without changing
BlueFerry transport or history policy.

**Source/build validation:** `cargo fmt --check --manifest-path rust/Cargo.toml
--package mseries-pantheon-kit --package mseries-messages`, `cargo check --locked
--manifest-path rust/Cargo.toml -p mseries-messages`, strict Clippy with warnings
denied, and `git diff --check` passed. No test suite or GUI render was run.
Next: inspect long runs, group sender changes, day boundaries, invalid
timestamps, and narrow windows on the owner session. Phone and accessibility
acceptance remain open.

## Rust Messages optimistic send feedback — 2026-10-22

Rust Messages now places an outgoing bubble in the conversation as soon as a
send starts. It marks successful MAP transfer accurately as transfer to the
iPhone, then keeps the bubble until BlueFerry history echoes a matching outgoing
body. Matching accounts for earlier identical pending sends, preventing a
temporary duplicate while history catches up. Known failures remove the
optimistic bubble and keep the draft; unknown outcomes keep both and tell the
user to check the iPhone before retrying. The session-only outbox is capped at
128 unresolved messages.

**Source/build validation:** `cargo fmt --check --manifest-path rust/Cargo.toml
--package mseries-pantheon-kit --package mseries-messages`, `cargo check --locked
--manifest-path rust/Cargo.toml -p mseries-messages`, strict Clippy with warnings
denied, and `git diff --check` passed. No test suite or GUI interaction was run.
Next: inspect pending, transferred, echoed, failed and unknown-outcome states in
a private UI fixture, then repeat with a paired iPhone. Delivery receipt claims
remain unsupported by MAP.

## Rust Messages keyboard navigation parity — 2026-10-22

Added an accessible application menu with a keyboard-shortcuts sheet, F5
refresh, and Alt+Left back navigation. The compact Back button and Escape now
clear the selected conversation while retaining its draft; Ctrl+F still opens
the conversation list without discarding the current selection. Local locked
compile and strict Clippy checks are recorded with the follow-up commit. GUI and
keyboard interaction acceptance remain open. Sidebar rebuilds no longer select
the first conversation implicitly; this avoids opening it and marking it read
without user action.

## Disk Space SDK scaling pass — 2026-10-22

Disk Space now uses SDK text-relative spacing and margins for persistent layout
groups, font-relative GTK CSS padding for repeated rows, and SDK accessible
names for its icon-only actions, filesystem navigation list and current-folder
contents list. No scanning, selection, Trash or permanent-delete behavior
changed. Fixed three-pane minimum widths and compact-window navigation still
need an interaction redesign and visual qualification.

**Source/build validation:** `cargo fmt --check --manifest-path rust/Cargo.toml --package mseries-diskspace`,
`cargo check --locked --manifest-path rust/Cargo.toml -p mseries-diskspace`, and
`git diff --check` passed. No app test suite or GUI render was run after this
change. As of 17:46 UTC, current-head Messages, SDK/System Monitor and Software
Updates workflows had started; Disk Space and broad wiring runs were queued.
No current-head app test result was complete. The prior Disk Space run was
cancelled as the branch advanced. Next: inspect light/dark and narrow-window
rendering, then implement and qualify compact pane navigation.

## Rust Messages public link previews — 2026-10-22

The preview now supports public HTTPS images, including GIF/WebP, and YouTube
links. Incoming previews require an explicit Load Preview action; sent links
can load automatically. Requests validate and pin public DNS addresses, bound
response bytes, dimensions, animation frames and in-memory cache, and never
write previews to disk or fetch MAP attachments. This closes the earlier
bounded-preview implementation gap; phone, keyboard/accessibility and owner
acceptance remain open.

The main window also supports Ctrl+F (search), Ctrl+R (refresh), Ctrl+N (new
message) and Escape (clear focused search or return to the compact conversation
list). Search, conversation list, favorite control and composer have SDK
accessible names. The conversation header can explicitly copy recipient
addresses to the clipboard. The Send button stays available; Ctrl+Enter is an
alternate send action when sending is enabled, while Enter inserts a newline.
The startup error screen also has a Retry action that closes the placeholder and
reactivates Messages, so an unavailable BlueFerry API can be retried in place.

**Source/build validation:** `cargo fmt --check --manifest-path rust/Cargo.toml --package mseries-messages`,
`cargo check --locked --manifest-path rust/Cargo.toml -p mseries-messages`, and
`git diff --check` passed. No Messages test suite or GUI probe was run for this
keyboard, clipboard-action and retry change. Full interaction and
assistive-technology review remains open.

## Lock screen restyled like elementary's greeter — 2026-10-22 (Claude Code)

Owner asked for gtklock to look like elementary: wallpaper, fonts, clock and password field. **Installed nowhere,
unqualified until the session package is installed and the next login.**

- **`/usr/bin/pantheon-lock`** (session package) runs gtklock with `usr/share/pantheon-rust-compositor/lock/layout.ui` and
  `style.css`: the user's wallpaper (`picture-uri`, or `-dark` in dark mode), io.elementary.greeter's clock and date
  styling (values from its `Application.css`), and a Granite-style card with an accent-coloured avatar initial (or the
  AccountsService/`~/.face` picture), the user's name, and a password field with an accent arrow button. It follows the
  12/24 h clock, the accent from `gtk-theme`, and `color-scheme` (GTK `:dark` variant). gtklock's widget ids and handlers
  are kept, so PAM, Caps Lock and error messages still work. Any failure falls back to stock gtklock.
- **Default locker:** the compositor uses `/usr/bin/pantheon-lock` when installed, else `gtklock`;
  `PANTHEON_LOCK_COMMAND` still wins.
- **Correction to the entry below:** the earlier idle probe never gave the nested window X keyboard focus, so it proved
  frame callbacks, not that typing reached the lock screen. The probe now focuses the window and requires key events:
  with the fix 12 key events and 9 frame callbacks while typing; the control build (no lock-surface callbacks) also gets
  12 key events but 0 callbacks, and its screenshot shows the card frozen mid fade-in with no dots — the owner's
  "no keyboard feedback". With the fix, dots appear as you type.
- **Verified:** strict clippy both ways, 176 tests (new: default lock command); idle probe 6/6; screenshots with
  `lock-probe/shoot.sh` in light (owner's settings) and dark: locked, revealed, typing, Caps Lock warning. No password was
  submitted in any test.
- **What to check at the next login (after installing the package):** Super+L shows your wallpaper, the big clock and the
  card; typing shows dots; Caps Lock shows the warning; your password unlocks. If it misbehaves:
  `Environment=PANTHEON_LOCK_COMMAND=gtklock` drop-in restores the stock look.
