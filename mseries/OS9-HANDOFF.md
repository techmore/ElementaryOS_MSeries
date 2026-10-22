## Signal/Messages transition slice and Rust Pantheon target — 2026-10-22

The official ARM64 Signal Electron client now refreshes its system-accent patch
when the installed launcher opens it. A mutable user install is recolored only
when the current accent differs from the saved accent; the original `app.asar`
remains the restore source. Atomic releases are intentionally left unchanged so
their content hash stays intact. This remains the transition path, not the target
Rust Pantheon client. The real shelf-to-compose attachment preview,
logged-in appearance and display-session boundary still require owner-session
acceptance; keep issue #227 open.

Messages adds local Add/Remove from Favorites actions to conversation menus.
Favorites are stored in the desktop keyring per connected phone, direct chats
follow a unique normalized address across inbox promotion, and imported Mac pin
order remains a separate read-only snapshot. No phone, account, installation or
running session was changed. Shell syntax and Python byte-compilation pass; the
Wingpanel Vala module builds against GTK 4.22 and Wingpanel 8.0.4, with two
existing `Gdk.Texture.for_pixbuf` deprecation warnings. The Messages app was not
opened and its test suite was not run.

Owner clarified the destination: first-party apps should follow the Rust GTK4 / Granite-rs pattern of `rust/claude-pantheon-rs` (the T3 Code client). Messages can move its UI to Rust over BlueFerry's existing versioned session-D-Bus API, keeping BlueFerry as the sole MAP client and encrypted-history owner. Signal remains gated on an officially supported secure client/backend boundary; do not treat `libsignal` alone as a stable external SDK or touch its private profile. Plan: [`SIGNAL-PANTHEON-DESIGN.md`](SIGNAL-PANTHEON-DESIGN.md). Next implementation slice: a Rust Messages client/adapter in the `rust/` workspace; retain the current launcher until feature parity and owner-session phone acceptance. The real Signal screenshot preview/appearance and Messages live visual/keyboard/accessibility gates also remain open.

## Signal accent follows the elementary palette — 2026-10-22

Owner clarified that stock Pantheon/elementary defaults are the source-of-truth
baseline; the custom Pantheon-R pastel palette needs a separate contrast audit. Signal now
maps system accents to the published elementary palette stops. Blue uses
`#3689e6` (500), `#8cd5ff` (100), `#64baff` (300), `#0d52bf` (700), and
`#002e99` (900). Accent labels use dark/light stops for light/dark appearance;
white-on-accent actions and outgoing message bubbles use the high-contrast 900
stop. Other named accents now use the elementary stylesheet's matching 500 and
100/300/700/900 stops as well. Palette source: elementary/stylesheet
[`_palette.scss` at `64dea31`](https://github.com/elementary/stylesheet/blob/64dea31d6711bdd2f53903ec8441a5f89ac0edd0/src/gtk-4.0/_palette.scss).

The patcher edits only Signal's manifest and Tailwind stylesheets, startup-window
accent, and embedded logo fills. It no longer scans arbitrary JavaScript, images, or fonts,
so chat colors, avatars, QR artwork, and sticker palettes remain intact. The
fixed-width archive entries retain their offsets and have refreshed integrity
hashes. The latest local reapplication changes 201 uses in four packaged files.
Unit coverage checks light/dark and high-contrast tokens, contrast for
all named action fills, asset preservation, and archive hashes. No phone/account
data was read or changed. Atomic deployments and the separate Flatpak remain
unmodified. The Signal Beta system install uses the revised palette at the next
launch. Screenshot-shelf acceptance remains tracked under issue #227.

## Signal screenshot shelf batches recent images — 2026-10-22

The screenshot shelf now keeps recent captures in one transient card and offers
up to the 12 newest images together as a GTK file list. The thumbnail and
visible count update to the latest capture. Copy acts on the newest image;
Show reveals every capture in the current batch. Saved originals remain in
Downloads/Screenshots, including after accepted, refused or cancelled drags.
Each image gets its own retained staging copy and, for running Flatpak targets,
its own document-portal export.

The card now reads GTK theme background and foreground colors, so light/dark
appearance follows GTK rather than the previous fixed dark surface. Source
screenshots were inspected in both modes. Ten isolated Xvfb/private-D-Bus
retention tests pass, including native and Flatpak multi-file list creation,
the 12-image cap and retention of every original. Python byte-compilation,
shell syntax and git diff checks pass. This does not verify that Signal
actually attaches every image: compose preview, paste behavior and the
XWayland-to-Wayland owner-session path remain open under issue #227. No Signal
account was opened and no message was sent.

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
