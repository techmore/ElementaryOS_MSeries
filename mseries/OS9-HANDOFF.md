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

## Signal accent aligned with Pantheon-R — 2026-10-22

The official mutable Signal Beta app now follows Pantheon-R's softened blueberry
ramp: brand and primary accents `#9dbfe3`, pressed controls `#7ba2cc`, and dark
variant `#a9c8e8`. The default AccountsService blue maps to this theme palette
instead of elementary's more saturated `#3689e6`; other selected system accents
remain supported. The desktop launcher refreshes the palette before each launch.

Applied through the existing Signal integration after confirming Signal Desktop
was closed. The original `app.asar.orig` remains available for restore; 265 uses
across 26 packaged assets now use the Pantheon-R palette and the bundle's
internal integrity hashes were refreshed. No phone/account data was read or
changed. Atomic deployments and the separate Flatpak remain unmodified. Check the
appearance at the next Signal Beta launch; screenshot-shelf acceptance remains
tracked separately under issue #227.

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
