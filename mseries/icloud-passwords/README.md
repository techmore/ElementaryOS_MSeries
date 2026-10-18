# Apple Passwords — optional experiment

This ARM64 desktop feature is disabled by default. Image payloads carry only the
installer and public extension identity; no accounts, tokens, passwords, container
identity or private keys belong in the image or repository.

## Enable

As the logged-in desktop user, without sudo:

```sh
bash mseries/install-icloud-passwords.sh --experimental
```

Prerequisites: native Brave, Python 3.10+ with venv/pip support, git, rootless Podman,
a systemd user session, GTK 4/Granite 7 with system Python GI bindings, and an unlocked GNOME Keyring/Secret Service. This initial
container digest supports ARM64 only. Installation downloads dependencies and the
helper image; no Apple credentials are requested by the installer.

## Finish Brave setup

1. Open `brave://extensions`, enable **Developer mode**, and choose **Load unpacked**.
2. Select `~/.local/share/mseries/icloud-passwords/source/extension`
   (or `$XDG_DATA_HOME/mseries/icloud-passwords/source/extension` if configured).
3. Confirm **Apple Passwords**, ID `hagjmolifioccmojhoplpopjklljajno`, is enabled.
4. Open **Apple Passwords (Experimental)** from Applications, or run:

```sh
~/.local/bin/mseries-icloud-passwords-gui
```

Enter your Apple account email and password in the native window, then follow its
verification-code and trusted-device prompts. Recovery requires a separate unchecked
consent box before you enter the selected device’s known passcode. The GUI never
automatically repeats a recovery attempt. Cancellation and closing are blocked while
a submitted recovery attempt is in flight. Enter credentials directly in the app. Never paste these in chat or public logs. Keep a trusted Apple
device available. Upstream warns that too many wrong recovery passcodes can
permanently lock recovery: stop on an unexpected failure, do not guess or loop
login attempts. Advanced Data Protection remains unqualified.

After successful sign-in, the native window displays a searchable saved-login list
and masked password details with an explicit reveal control. **Sync Now** refreshes
the snapshot. The header follows elementary light/dark preferences. The terminal
client remains available as `~/.local/bin/mseries-icloud-passwords login|show|sync|logout`.
Use the Brave extension for live autofill and saved TOTP codes. Browser use can
trigger a refresh after six hours. The GUI does not display TOTP or Hide My Email yet.
Never capture real credentials in test screenshots or diagnostics.

The GUI does not save your Apple password unless you enable **Remember password**.
That optional encrypted storage supports background token renewal and Hide My Email;
without it, some renewals require signing in again. IPC carries secrets over private
child pipes only; no password argv/environment fields, raw server errors or protocol
logging. GUI error messages expose only known failure categories and numeric codes.

The extension has access to HTTP/HTTPS pages for autofill. It reads a local encrypted
snapshot, and can show existing Hide My Email aliases. It does not save edited/new
passwords to iCloud, implement passkeys or fill native desktop applications. Joining
iCloud Keychain registers a client/trust identity; read-only refers to password
content, not an absence of account authentication or device registration.

## Local storage and service

- Client/source/venv: `~/.local/share/mseries/icloud-passwords/source` (XDG-aware).
- Encrypted account/vault data: `~/.config/icp` (upstream, XDG-aware).
- Master key: GNOME Keyring; this port disables upstream's file-key fallback.
- Helper: `mseries-icloud-anisette.service` under the user systemd instance.
- Helper network listener: `127.0.0.1:6969`; never exposed to the LAN.
- Helper identity: rootless Podman volume `mseries-icloud-anisette`, preserved across
  restarts. Do not delete it during routine upgrades.
- Native messaging registration: Brave's `NativeMessagingHosts/org.icp.native.json`.
- GUI: `~/.local/share/mseries/icloud-passwords/gui` and `~/.local/bin/mseries-icloud-passwords-gui`.
- Private-service CA roots: downloaded over verified HTTPS from Apple PKI with pinned
  DER SHA-256 digests, combined with system roots in a client-only `ca-bundle.pem`.
  Certificate verification is enabled in all patched authentication paths; the
  operating system trust store is unchanged.
- Installation receipt: `~/.local/share/mseries/icloud-passwords/installation.json`.

An unlocked user session can access the vault through the host. No extra lock-screen
or biometric gating is implemented here. The container service runs only after
explicit installation; default first-boot jobs never enable it.

## Disable / remove

Disable the extension in `brave://extensions` and stop automatic helper startup:

```sh
systemctl --user disable --now mseries-icloud-anisette.service
```

The native **Sign Out** action clears the local session and cached passwords/aliases.
It keeps the client and helper identities and does not revoke account devices.
The terminal `~/.local/bin/mseries-icloud-passwords logout` retains upstream behavior:
it clears the session but keeps the downloaded vault. Disable the extension when
disabling the feature, since it reads this cache independently of the GUI.
Upstream also supports `logout --wipe-device` to forget its local device identity;
this is not represented as revoking a device from Apple's account website.
The installer leaves encrypted data and the Podman volume in place when disabled.
Remove the `org.techmore.mseries.ApplePasswords.desktop` launcher and the dedicated
Brave native-host JSON if uninstalling. Re-enable by rerunning the opt-in installer.

## Sources / changes / qualification

- Client: https://github.com/Sank6/iCloud-Keychain-for-Linux
  at `916ef17a5a14965f353d556a53ca3eedc1439113`, MIT. The cloned source retains
  `LICENSE.md`; upstream code is fetched, not vendored in the OS repository.
- Authentication helper: https://github.com/Dadoum/anisette-v3-server
  ARM64 image `docker.io/dadoum/anisette-v3-server@sha256:12ebe8bedbffe96953ce4fd20b578997bc7ed266f7a5015d4f96526e9c65af1f`.
- Local modifications: require Secret Service, adapt the shared Firefox/Chromium
  manifest to Chromium MV3, add a stable public extension key. That public key is
  an identity seed, not an encryption key; no corresponding private key is stored.
- Python dependencies follow upstream's minimum constraints and are not locked;
  client and helper pins do not imply an independently audited dependency chain.

2026-10-18 local verification: installer and repeat installation succeed on
Python 3.14 / elementary OS 9 / ARM64; helper HTTP 200 with valid JSON; loopback-only
listener; GNOME Keyring unlocked; native protocol ping with an isolated empty vault;
92 upstream host/TOTP/keychain crypto/escrow SRP/Octagon-key tests plus 11 subtests;
three integration contracts including unavailable-keyring rejection, stable extension
identity and patch-drift rejection. Shell syntax and shellcheck pass.

Not yet verified: loading the extension in the owner's Brave UI, actual Apple login,
keychain recovery, password download, live autofill, TOTP, Hide My Email, ADP, reboot
behavior, or factory-image boot. The owner's authentication and live test are next.

## Native GUI and failed-login follow-up — 2026-10-18

The owner’s first terminal attempt failed at GSA init with `ec=-80045`, before
2FA or recovery. No recovery passcode was submitted by that attempt.
[anisette-v3-server issue 61](https://github.com/Dadoum/anisette-v3-server/issues/61)
reports an endpoint-specific client-description workaround. This integration applies
its Windows descriptions to GSA, loginDelegates and escrow, retaining the original
Mac descriptions for account settings and CloudKit. This is a reported workaround,
not proof that this account can now sign in, and Apple can change acceptance again.

Added native GTK 4/Granite 7 sign-in, private worker prompts, explicit recovery consent,
snapshot search/reveal, last-sync display, Sync Now and local sign-out. Deprecated
terminal setup/sync shortcuts are replaced by one native Applications entry.
`worker.py` does not expose authentication records or TOTP seeds to the GUI.

Upstream disabled certificate verification for GSA/iCloud/web auth; this port now
enables it and scopes [Apple PKI](https://www.apple.com/certificateauthority/) roots
to the client bundle. Plain HTTPS probes without account data verified GSA, setup
and idmsa TLS successfully. `gsa-errors.patch` adds safe non-plist/transport error
handling so server failures do not crash onboarding.

Validation: ten offline GUI/IPC/keyring/CA-pin integration tests, four mocked endpoint
identity/TLS/consent tests in the client venv, and 129 upstream tests plus 11 subtests.
One upstream fixture hardcoding the original Mac escrow header is deselected; its
updated Windows-header and no-consent/no-network contract is covered by
`test_network.py`. Repeat installation and compiled Python/shell checks pass.
Native window constructed under Xvfb; installed native process launched locally.
No real account authentication was attempted by the agent. Successful sign-in,
recovery, sync, live autofill, ADP and factory-image boot remain unverified.


### Approval/code waiting fix — 2026-10-18

Owner reports phone approval arrives but Linux fails before code entry. The native
worker now offers the code dialog before waiting on the trusted-device notification
HTTP response. Code entry waits on the private input pipe without a user-entry timeout;
there is only one code dialog and one notification request. A notification read timeout
continues to normal code validation without resending; TLS, connection and explicit
HTTP errors remain fatal. Errors now retain a safe stage label. No recovery behavior
or retry budget changed. This addresses a demonstrated timeout path, not a proven
root cause of the owner’s current failure.

Three mocked tests cover prompt-before-response, one-request read-timeout handoff,
and fatal TLS failure. Six native GUI/IPC tests pass. Installed the updated worker
and notification patch for the next owner-initiated sign-in. Live authentication
and sync remain unverified; no credentials or codes were entered by the agent.
