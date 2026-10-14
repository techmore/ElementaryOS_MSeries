# Tether continuity for elementary OS M-Series

Status: pinned optional-package integration implemented; not installed on the
host or added to the base image. Target hardware is the MacBook Pro 14-inch M1
Pro running elementary OS 9 on Asahi. Desktop and phone qualification is still
required.

## Product goal

Give the laptop an iPhone-connected messaging and code handoff experience:

- Read and reply to SMS and iMessage conversations from elementary OS.
- Receive one-time verification codes from iPhone messages and send them to a
  matching browser sign-in flow, including Brave.
- Pair directly with the iPhone. Do not require an always-on Mac, server, or
  other relay machine. The phone and laptop need to be available and connected
  for live mirroring; this is not an iMessage cloud client or offline inbox.
- Keep this as an optional desktop add-on. It must not enter the factory image
  until ARM64, elementary's Wayland session, browser integration, and the actual
  iPhone are qualified.

## Candidate: Tether

The upstream [Tether project](https://github.com/zackb/tether) describes an
iPhone-to-Linux connection with SMS/iMessage messaging over Bluetooth and
clipboard, file, and OTP flows over Wi-Fi. Its iOS app and Linux desktop pair
directly. Its browser extension can offer OTPs from iPhone messages and the iOS
share sheet. This architecture does not use a Mac relay.

The project documents Chromium-based browsers and Firefox, but does not name
Brave in its supported-browser list. Brave is Chromium-based, so extension
compatibility is plausible; installation, native messaging, permissions, and
OTP fill behavior in Brave are qualification items, not established support.
Likewise, the upstream's reported stable features are not proof that the
current elementary/Asahi stack or this M1 Pro is compatible.

The current host reports BlueZ 5.85. Upstream requires BlueZ 5.86+ with the
experimental bearer API for Bluetooth messages, so SMS/iMessage is blocked on
this host until the OS provides a compatible BlueZ. The integration does not
upgrade BlueZ. The upstream v0.2.38 ARM64 Debian package is pinned to source
commit `5850727002bff150c6e11dc2b309626e0a919014` and release SHA-256
`eec8892093cbca2062739080f381a594006f9437abd1374f2087b936877257ae`. The
upstream repository and extension identify MIT licensing. Install and Brave
registration instructions are in [`tether/README.md`](tether/README.md).

### Integration shape

1. Package Tether as a removable, user-selected add-on, separate from the base
   OS and from elementary's default messaging app.
2. Keep the upstream Debian package pin and digest recorded. The upstream
   repository carries the Linux daemon/UI and browser extension under MIT;
   check App Store licensing independently before redistributing the iOS app.
3. Start the user service only after explicit pairing/setup. Do not enable
   unattended Bluetooth discovery or pair devices without user action.
4. Install the browser extension only when requested. Its Chromium manifest
   requests all-website access; explain this permission and require the user to
   review Brave's permission prompt.
5. Provide an uninstall/rollback path that removes the app, service, browser
   integration, and Tether's local pairing data without touching unrelated
   Bluetooth pairs. Explain that the OS-level Bluetooth bond must be forgotten
   separately.

## Acceptance before calling the core experience ready

- Pair and reconnect the user's iPhone with the M1 Pro over the documented
  transport; show that no other always-on computer participates.
- Receive and reply to SMS and iMessage, including a new conversation, and
  verify behavior for group threads, attachments, phone lock, Bluetooth range,
  suspend/resume, and temporary disconnection.
- Verify OTP handoff from an iPhone message and the iOS share sheet into a
  login form in Brave. Confirm the source/site matching behavior and that codes
  are not sent to unrelated origins. Upstream currently polls for OTP fields
  and can autofill automatically; treat the broad host permission and fill
  behavior as an explicit opt-in and review before recommending it.
- Check whether the required Bluetooth experimental features and Wayland
  clipboard protocol are available in the actual elementary session. The
  upstream currently documents BlueZ 5.86+ with its experimental bearer API
  for messaging/notifications and `wlr-data-control` for clipboard sync; these
  are explicit compatibility checks, not dependencies to silently enable.
- Confirm the upstream's iOS-version caveats on the owner's iPhone. In
  particular, upstream documents notification mirroring as unavailable on iOS
  18 and earlier; do not conflate that with message support.
- Verify credentials and message data remain local to the paired devices,
  document the transport/encryption behavior from upstream, and provide a
  clear unpair/data-removal action.

No iPhone/Brave acceptance checks have been run. The installer and Brave helper
are implemented but have not been executed on the host.

## Optional add-ons

### AirDrop-style file transfer

Treat this as a separate, lower-priority add-on. LocalSend is the known
cross-platform, same-network AirDrop-style option used in the Omarchy Mac
reference; it is not Apple's native AirDrop protocol. Keep it independent of
Tether so file transfer can be installed or removed without affecting
messages. Native Apple AirDrop compatibility is a distinct research item and
must not be implied by LocalSend support.

### Touch ID for authentication

Track this separately from messaging. Linux fingerprint login/PAM and passkeys
(WebAuthn/FIDO credentials) are different authentication paths; do not label
Touch ID as a passkey unless a verified implementation actually exposes that
flow. First identify a working M1 Pro Secure Enclave/Touch ID driver and
firmware, enrollment flow, and PAM integration on the exact kernel. Keep the
password fallback and do not make biometrics mandatory. Current M1 Pro support
is not verified; see [Desktop Setup](DESKTOP-SETUP.md#touch-id-on-m1-pro).

## Source and boundary notes

- Tether upstream: <https://github.com/zackb/tether>.
- Omarchy's LocalSend reference: <https://github.com/omacom/omarchy/blob/quattro/manual/22-guis.md>.
- Touch ID status: [Desktop Setup](DESKTOP-SETUP.md#touch-id-on-m1-pro) and
  [Omarchy audit](OMARCHY-AUDIT-2026-10.md).
- Do not copy Omarchy's Arch packages or change the base ISO as part of this
  proposal. Follow [Port Map](PORT-MAP.md) and pin/record source and licenses
  before code is vendored, built, or packaged.
