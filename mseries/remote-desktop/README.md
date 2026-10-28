# Remote Desktop (WebRTC) — phone view and control for this computer

Rust WebRTC host for the elementary OS M-series desktop. A phone opens a one-time
link (or scans a QR), the person at the computer taps **Allow**, and the phone sees
the screen over WebRTC H.264 and, only if allowed, controls it with touch.
Scope: POS management, desktop and support use — never healthcare.

```
phone browser ──ws signalling──▶  mseries-remote-hostd  ◀── D-Bus ──▶ Remote Desktop app
      ▲   (hello: invite/resume)        │  consent · audit             Wingpanel indicator
      └──── WebRTC: H.264 video ◀───────┘  capture · encode            Work Mode taskbar
            + "input" data channel ──▶ input gate ──▶ Mutter RemoteDesktop
```

| Piece | Where | Notes |
|---|---|---|
| Protocol, invites, consent state machine, audit, input gate, capture, H.264 | `crates/remote-core` | pure/synchronous, 32 unit tests |
| WebRTC host + headless viewer (webrtc-rs 0.21) | `crates/remote-rtc` | real DTLS/SRTP/SCTP loopback tests |
| Daemon, signalling listener, phone web client, D-Bus, Mutter backend | `crates/remote-hostd` | `mseries-remote-hostd`, `tm-remote-viewer` |
| Native GTK 4 / Granite 7 app, consent prompt, Wingpanel indicator | `native/` | meson; Xvfb render probe |
| Work Mode taskbar anchor | `../dock-taskbar/TaskbarRemote.vala`, `../patches/dock-taskbar-remote.patch` | same indicator class as the panel |
| Install | `../install-remote-desktop.sh` | user-level; nothing starts or listens by default |

## Safety model

* **Off by default.** Nothing listens until the owner turns on *Allow remote access*; turning it off ends the session, revokes invites and closes the port.
* **Three yeses.** The owner makes the link (single-use, 128-bit, 5 min, in the URL fragment so it is never logged), the owner answers the consent prompt on the computer (Deny is the default; it declines by itself after 60 s), and **control is a separate choice** from view-only. A view-only link can never be upgraded.
* **One viewer at a time**, resume token valid only for the live session and a 30 s grace period; idle (30 min) and length (8 h) limits.
* **Input gate** validates and rate-limits every event, re-checks permission per event (a downgrade applies immediately, held buttons/keys are released) and refuses input while the desktop is locked (logind `LockedHint`, fail-closed).
* **Nothing is recorded.** Frames live only in memory. The audit log (`~/.local/state/mseries/remote-desktop-audit.jsonl`, mode 0600) holds who/when/permission, the viewer **IP address**, **connection time** and a **link-quality summary** per session (connect ms, streamed seconds, frames sent/dropped, average kbit/s) — never secrets, frames or typed text. Quality is aggregated from counters at session end; no per-frame logging or probing.
* Same-origin check on the WebSocket, strict CSP on the page, bounded messages, 4 concurrent unauthenticated sockets.

## Use

```sh
bash mseries/install-remote-desktop.sh          # user-level install, remote access stays off
bash mseries/install-remote-desktop.sh --panel  # + Wingpanel module (sudo; loads at next login)
mseries-remote                                   # app: switch on, Create Link, scan, approve
mseries-remote-hostd check                       # readiness report
mseries-remote-hostd ctl status|invite|approve ID|control on|stop   # scripting
tm-remote-viewer "<link>" --seconds 10           # headless viewer for support diagnostics
```

Reach: use the **Tailnet** link (WireGuard-encrypted) or the LAN link. The page is plain
`http`; media is always DTLS-SRTP, but on an untrusted LAN put `tailscale serve` (HTTPS) in front.
Phones on another NAT need `stun`/`turn` in `~/.config/mseries/remote-desktop.toml`
(see `deploy/remote-desktop.example.toml`).

**Phone:** open the link in Safari/Chrome. One finger moves the pointer, tap = click,
two-finger tap = right-click, two-finger drag = scroll, tap-then-drag = drag; ⌨ types,
the key tray sends Esc/Tab/arrows and Ctrl/Alt/Super chords; *Touchpad/Direct* switches
relative vs absolute pointing. It reconnects with backoff and ICE restart after network changes.

## Both desktop modes

Native elementary OS: Wingpanel indicator (`native/indicator`) + app. Windows Work Mode
hides the top bar, so the dock build embeds the same indicator class as a taskbar anchor
(`TaskbarRemote`, hidden until sharing is on). The consent prompt is a normal dialog plus
an urgent notification, so it appears in either mode. Work Mode is a skin of the same
elementary session, so there is one host; a literal Windows 11 guest VM would need a
Windows capture/input backend behind the same `Backend` trait (not built).

## Tests (all headless; none opens a window on the owner's screen)

```sh
cd mseries/remote-desktop
cargo fmt --all --check && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace
scripts/smoke-headless.sh <target-dir>                                    # daemon + D-Bus + Rust viewer, private bus
NODE_PATH=<node_modules with playwright-core> scripts/smoke-browser.sh <target-dir>   # headless Chrome phone, touch input
meson setup b native && ninja -C b && meson test -C b                     # native model tests
```

## Status — what is and is not verified

Verified here (2026-10-21, j314s, headless): 32 core + 10 daemon unit + 5 daemon e2e + 4 WebRTC loopback tests
(video decoded and ordered over real UDP/DTLS, input round trip, view-only enforcement, ICE restart,
resume after drop, owner stop, deny, single-use invites, cross-origin refusal, audit contents);
D-Bus smoke; headless **Chrome (mobile emulation + touch)** decoding the stream and delivering
tap/drag/right-click/typing; Mutter D-Bus marshalling against a fake service built from mutter's
interface XML; GTK renders (light/dark); full pinned dock build with the taskbar anchor.

**Not verified on hardware:** capture and input on a live **Gala/Mutter** session (the owner's current
session is the experimental Rust compositor, which exports neither interface); real phone/iOS Safari;
NAT traversal/TURN; Wingpanel module and taskbar anchor loaded in the live shell; long-run stability;
suspend/resume; software H.264 CPU cost on the M1 Pro (no measurement taken; Asahi has no hardware encoder);
audio (not implemented). The earlier Node/Python prototype on `feat/webrtc` is superseded by this
implementation and was not modified.
