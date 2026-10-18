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
a systemd user session and an unlocked GNOME Keyring/Secret Service. This initial
container digest supports ARM64 only. Installation downloads dependencies and the
helper image; no Apple credentials are requested by the installer.

## Finish Brave setup

1. Open `brave://extensions`, enable **Developer mode**, and choose **Load unpacked**.
2. Select `~/.local/share/mseries/icloud-passwords/source/extension`
   (or `$XDG_DATA_HOME/mseries/icloud-passwords/source/extension` if configured).
3. Confirm **Apple Passwords**, ID `hagjmolifioccmojhoplpopjklljajno`, is enabled.
4. Open **Set Up Apple Passwords (Experimental)** from Applications, or run:

```sh
~/.local/bin/mseries-icloud-passwords login
```

Enter your Apple account password, 2FA code and requested device passcode directly
in that terminal. Never paste these in chat or public logs. Keep a trusted Apple
device available. Upstream warns that too many wrong recovery passcodes can
permanently lock recovery: stop on an unexpected failure, do not guess or loop
login attempts. Advanced Data Protection remains unqualified.

After successful sign-in, click the extension on a site with a saved login. Test
one known username/password, then a saved TOTP code if available. **Apple Passwords
(Experimental)** opens the searchable terminal vault; **Sync Apple Passwords
(Experimental)** refreshes it. Browser use can trigger a refresh after six hours.
Never capture real credentials in test screenshots or diagnostics.

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
- Installation receipt: `~/.local/share/mseries/icloud-passwords/installation.json`.

An unlocked user session can access the vault through the host. No extra lock-screen
or biometric gating is implemented here. The container service runs only after
explicit installation; default first-boot jobs never enable it.

## Disable / remove

Disable the extension in `brave://extensions` and stop automatic helper startup:

```sh
systemctl --user disable --now mseries-icloud-anisette.service
```

To sign out locally, run `~/.local/bin/mseries-icloud-passwords logout`.
Upstream also supports `logout --wipe-device` to forget its local device identity;
this is not represented as revoking a device from Apple's account website.
The installer leaves encrypted data and the Podman volume in place when disabled.
Remove the three `mseries-icloud-passwords-*.desktop` launchers and the dedicated
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
