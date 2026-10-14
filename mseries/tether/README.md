# Tether add-on for elementary OS M-Series

This optional integration installs upstream Tether's ARM64 Debian package. It
is not part of the factory image, and this project does not modify upstream
Tether source.

## Install the desktop app

From the repository root:

```sh
bash mseries/install-tether.sh
```

The installer downloads upstream v0.2.38's `arm64.deb`, verifies its published
SHA-256 (`eec8892093cbca2062739080f381a594006f9437abd1374f2087b936877257ae`),
and asks apt to install the package and resolve dependencies. Source commit:
`5850727002bff150c6e11dc2b309626e0a919014`. The upstream project and extension
are under its MIT license; see the [upstream license](https://github.com/zackb/tether/blob/v0.2.38/LICENSE)
and [release](https://github.com/zackb/tether/releases/tag/v0.2.38).

This script does not start or enable `tetherd`, configure BlueZ, open the
firewall, or install a browser extension. Launch Tether manually from
Applications or run `tether-gtk`, then install the iPhone companion from the
App Store and approve pairing on both devices. Tether uses direct iPhone to
laptop connections; it does not need a relay Mac. The laptop must be on and
reachable while you use the live connection.

Run `bash mseries/install-tether.sh --status` to see whether the local BlueZ
version meets Tether's message transport requirement. Tether requires BlueZ
5.86 or newer and its experimental bearer API for iMessage/SMS over Bluetooth.
On the current elementary OS 9 host, BlueZ is 5.85, so the messaging path is
not ready. This installer deliberately does not upgrade BlueZ. The app's Wi-Fi
and OTP features are separate, but Wi-Fi pairing requires TCP 5134 and mDNS
UDP 5353 to reach the laptop; no firewall rules are applied automatically.

## Optional Brave OTP handoff

Tether's Chromium extension is not listed as a Brave-tested extension. This
helper uses Chromium's unpacked-extension and native-messaging mechanisms in
Brave's per-user profile. Treat it as experimental until the real OTP flow is
confirmed.

1. Install the Tether desktop package as above.
2. Prepare the pinned upstream extension:

   ```sh
   python3 mseries/tether/brave-extension.py prepare
   ```

3. Open `brave://extensions`, turn on **Developer mode**, choose **Load
   unpacked**, and select the printed extension directory.
4. Review Brave's permission prompt. The extension requests access to all
   websites so it can detect OTP fields. Do not continue unless that permission
   scope is acceptable to you.
5. Copy the extension ID shown by Brave and register the native messaging host:

   ```sh
   python3 mseries/tether/brave-extension.py register EXTENSION_ID
   ```

6. Quit and reopen Brave. Pair Tether over Wi-Fi and explicitly test an OTP on
   a site you choose. Remove the extension in `brave://extensions` when done.

To remove the native host registration while leaving the app and extension
files in place:

```sh
python3 mseries/tether/brave-extension.py unregister EXTENSION_ID
```

The script only edits Brave's user-level native host manifest and preserves
other extension IDs registered to the same Tether host. It refuses to replace
a manifest for another executable. It does not manipulate Brave profiles or
enable Developer mode.

## Remove

```sh
bash mseries/install-tether.sh --uninstall
```

This removes the apt package and keeps Tether's pairing and local data. To
remove only the Tether XDG config/data/state directories later, use the
explicit `--purge-data` option. This does not remove the Bluetooth bond stored
by BlueZ; forget the laptop in the iPhone's Bluetooth settings and remove its
bond through the desktop Bluetooth settings if you want to unpair completely.
Unload the Brave extension in Brave and run the `unregister` command above
separately. The unregister command still works after removing the Tether app.
