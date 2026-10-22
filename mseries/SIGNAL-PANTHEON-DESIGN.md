# Rust Pantheon communications apps

## Target

The first-party Pantheon app suite should use Rust with GTK 4 and Granite-rs, following the existing `rust/claude-pantheon-rs` app (the T3 Code client) as its implementation and design reference. This request covers the T3 client, Signal and Messages as apps; it does not by itself change the compositor/session project.

Today, Signal is the signed official Electron client with a Pantheon launcher/tray/accent layer, and Messages is a GTK/Granite Python frontend. Those are working transition paths, not the Rust destination. Keep both usable until their replacements meet feature and owner-session acceptance.

## Messages: Rust frontend over BlueFerry

The Messages frontend can move to Rust without replacing the Bluetooth/message transport. The current Python client calls BlueFerry's typed `BackendClient`, which uses BlueFerry's session D-Bus API (`io.weirdware.BlueFerry.Messages1`). That interface exposes a versioned status and JSON thread/contact/inbox methods, as well as read and send operations. The Rust app should use that same daemon as the sole MAP client and implement a typed Rust adapter for the versioned D-Bus contract.

Preserve BlueFerry as owner of pairing, message routing, group-roster confirmation, encrypted history, send validation and retries. Port the existing UI and presentation behavior into the Rust app; do not create a second Bluetooth/MAP session or migrate message storage into the frontend. Keep the Python frontend available until the Rust app reaches parity and is accepted against the paired iPhone.

The reference bindings and app metadata live in `rust/claude-pantheon-rs/Cargo.toml`, its `data/` directory, and its GTK/Granite UI sources. The Rust app should follow the same accessibility, keyboard, light/dark, narrow-window and packaging standards.

## Signal: Rust UI needs a supported messaging boundary

The current Signal work is deliberately only an integration layer: signature-verified official ARM64 Signal Desktop, launcher identity, Wingpanel tray behavior and a reversible system-accent patch. It does not make Signal a native Rust app.

Signal Desktop is an Electron/TypeScript client. Signal's `libsignal` repository publishes Java, Swift and TypeScript bindings for Signal's own clients and says use outside Signal is unsupported and APIs may change without notice. `libsignal` by itself is not a supported GTK messaging SDK or an account/session API. A Rust app that opens Signal's private profile, shares its local database, reimplements its private network flows, or silently treats an Electron wrapper as the Rust UI would not meet the requested outcome.

Therefore the Rust Signal client is a separate upstream/API feasibility gate: identify an officially supported client API or coordinate a supported upstream client boundary before implementing a new UI. Keep the signed official client working as the transition path meanwhile. Do not claim a Rust port or migrate account data until the security, device-link, upgrade and rollback model is explicit.

## Delivery sequence

1. Build the Rust Messages frontend and BlueFerry D-Bus adapter in the `rust/` workspace. Preserve existing safety behavior and feature parity.
2. Run fixture and rendering checks, then owner-session visual, keyboard/accessibility and live iPhone acceptance before changing the default Messages launcher.
3. Resolve the Signal transport/API gate. Build the Rust client only on a supported boundary; keep the official client as the functional path until the new client passes account, messaging, update and rollback acceptance.
4. Integrate both Rust apps into the Pantheon desktop packaging/session path and keep their release and source provenance documented.

## Acceptance

- Messages preserves the existing conversation, contact, pin/favorite, group confirmation, draft, send/retry, read-state, media preview, keyboard and accessibility behaviors over the same BlueFerry service.
- Messages does not start an independent MAP client; pairing, encrypted history, routing and phone state remain owned by BlueFerry.
- Signal preserves the official supported cryptographic client path. A Rust interface does not become default until an officially supported backend boundary and data-safe migration/rollback path exist.
- Both apps pass light/dark, accent, keyboard, accessibility, narrow-window and live desktop acceptance in the Rust Pantheon session.
- Signal's actual screenshot shelf drop shows the expected compose preview and image content without sending; multiple images, paste fallback and the XWayland shelf → Wayland app case are recorded. Refused drops preserve the original for retry.

## Upstream references

- [Claude for elementary OS in Rust (T3 Code client)](../rust/claude-pantheon-rs/README.md)
- [Signal Desktop](https://github.com/signalapp/Signal-Desktop)
- [libsignal overview and API support statement](https://github.com/signalapp/libsignal)
- [Signal screenshot integration release gate (#227)](https://github.com/techmore/ElementaryOS_MSeries/issues/227)
