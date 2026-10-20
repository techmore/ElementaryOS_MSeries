# Microsoft Teams on elementary OS / Apple Silicon

Run Microsoft's actual Teams web client in a desktop app window. This is a local
launcher integration, not a native GTK reimplementation or a Microsoft-endorsed
wrapper. No custom Microsoft Graph app registration is required. The shortcut is
called **Microsoft Teams (Web)** in Applications.

## Use your existing Brave sign-in

```sh
bash mseries/install-teams.sh --use-brave-session --launch
```

This selects the last-used Brave profile at install time and keeps that selection
on subsequent reinstalls. Teams opens with `--app=https://teams.microsoft.com/v2/`
and `--profile-directory=…` in the regular Brave browser. Brave itself reuses its
Microsoft session and can offer saved passwords or passkeys. No authentication
databases are read, copied or exported. If Microsoft requires fresh authentication
or MFA, complete its normal sign-in flow. A Google/Brave account alone does not
provide a Microsoft account. Separate app-window/dock grouping depends on Brave
and the compositor; it is not guaranteed with a shared browser process.

Brave uses Chromium, but Microsoft does **not** name Brave on its supported
browser list. This mode is a convenience choice requested by the owner; qualify
sign-in, calls and sharing in the real tenant before relying on it for meetings.

## Microsoft-listed browser option

For an isolated supported-browser profile:

```sh
bash mseries/install-teams.sh --browser /usr/bin/google-chrome-stable --launch
```

Chrome and Edge on Linux are listed by Microsoft. The installer selects an
installed Chrome/Edge automatically for a fresh installation with no mode flags.
Reinstalling without flags preserves an existing choice. It never installs a
browser, changes the default browser, or copies an existing browser profile.

On ARM64 the official Google package is available at
<https://dl.google.com/linux/direct/google-chrome-stable_current_arm64.deb>.
Install it through apt so browser security updates use Google's package repository.
Record your default browser before installing: Google's package can select itself
as default, independently of this launcher. Restore your previous browser through
System Settings if necessary. On the owner's J314S, Chrome 155.0.8059.84 arm64 was
installed and Brave was restored as the default.

## Official Teams dock icon and Outlook Mail shortcut

The installer fetches Microsoft's current Teams website icon from
[Microsoft's own CDN](https://teams.public.onecdn.static.microsoft/evergreen-assets/icons/microsoft_teams_logo_refresh_v2025.ico).
The source asset is checksum pinned in `official_icon.py`; its 256-pixel PNG is
extracted unchanged from the ICO. No Microsoft image is committed to the repo.
The icon receipt is stored locally as `icon-source.json`. Offline upgrades keep
an installed official icon; a fresh offline install uses our generic fallback.
The installer rebuilds the local GTK icon cache so the dock can resolve it.

```sh
bash mseries/install-teams.sh --pin
python3 mseries/install-outlook-web.py
```

`--pin` adds Teams to the existing elementary dock launcher list once. The Outlook
installer replaces only the pinned `io.elementary.mail.desktop` entry with
**Outlook (Web)**, opening `https://outlook.office.com/mail/` in the selected Brave
profile. It keeps the existing elementary Mail icon and does not change the
system `mailto:` handler. The original ordered launcher list is retained in
`$XDG_CONFIG_HOME/mseries/outlook-web/dock-before.json`. Reinstalling preserves
that first backup and does not duplicate pins. No dock or panel restart is used.
Outlook mailbox authentication and message sending are not claimed as verified.

## Desktop and meeting links

The per-user installer writes the executable, icon and
`.desktop` entry beneath `$XDG_DATA_HOME` (normally `~/.local/share`). Configuration
is `$XDG_CONFIG_HOME/mseries/teams-web/config.json` (normally `~/.config`). In
isolated mode, its `profile/` directory has mode 0700 and is separate from your
normal browser. In Brave-session mode, the launcher does not create that profile.

The desktop entry advertises `msteams:` handling; it does not replace a selected
handler. Choose Microsoft Teams (Web) when the desktop asks which app should open
a Teams link. Official HTTPS links for `teams.microsoft.com`,
`teams.cloud.microsoft` and `teams.live.com` are accepted too. `msteams://` links
with one of those hosts are translated to HTTPS, retaining meeting parameters.
Other hosts, schemes and command-line flags are rejected.

No browser extensions, user-agent spoofing, disabled sandbox, automatic camera or
microphone permission, credential scraping, autostart, or panel restart is used.
Microsoft provides the web application and its updates; the browser provides its
normal password manager, notification and media permission controls. Offline use
and parity with every Windows/macOS Teams feature are not promised. Closing the
window follows the browser's lifecycle; this is not a separate background daemon.

## Diagnostics and removal

```sh
python3 "$HOME/.local/share/mseries/teams-web/mseries-teams" --check
python3 "$HOME/.local/share/mseries/teams-web/mseries-teams" --dry-run
bash mseries/install-teams.sh --uninstall
```

Uninstall removes the shortcut, launcher and icon. It preserves configuration,
Brave data and any isolated profile, so removing a launcher cannot erase sign-in
sessions. To sign out, use Microsoft's account menu inside Teams.

## Verification (2026-10-20)

```sh
python3 -B -m unittest discover -s mseries/teams-web -p 'test_*.py' -v
bash -n mseries/install-teams.sh
shellcheck mseries/install-teams.sh
desktop-file-validate "$HOME/.local/share/applications/org.techmore.mseries.TeamsWeb.desktop"
```

Fourteen offline tests exercise executable launch with a recording browser, desktop
Exec parsing through Gio (including spaces, percent signs, quotes and backslashes),
deep-link preservation/rejection, private profile permissions, diagnosis, corrupt
configuration, session-preserving upgrades/uninstall, and Brave profile reuse
without profile copying. They also cover official-icon checksum rejection, PNG extraction,
offline cache preservation, pinning and Outlook desktop dispatch. These tests do not authenticate or send messages.

Installed on the J314S with Brave 155.1.97.59 using its Default profile. The launch
command was dispatched to the browser and diagnostics confirm the selected mode;
the owner subsequently confirmed successful sign-in using the Brave workflow.
Dock grouping has not been visually qualified. A separate temporary in-app browser reached Microsoft's normal
sign-in page from the Teams URL; that is not proof of authentication in Brave.
Live message delivery, microphone/camera, notification delivery, screen sharing,
meeting join and suspend/resume remain unverified pending user sign-in and a real
meeting. No factory-image or hardware-media qualification is claimed.

## Sources

- [Microsoft Teams for Web: browser support and prerequisites](https://learn.microsoft.com/en-us/microsoftteams/teams-client-web)
- [Microsoft: use Teams on the web](https://support.microsoft.com/en-us/teams/meetings/use-microsoft-teams-on-the-web)
- [Google: Chrome for ARM64 Linux](https://blog.google/chromium/bringing-chrome-to-arm64-linux-devices/)
- [Google: Chrome installation](https://support.google.com/chrome/answer/95346)

Public documentation checked 2026-10-20. No Microsoft application code, branding
assets or browser binary is redistributed in this repository. The chat icon here
is original artwork; Microsoft Teams remains Microsoft's trademark.
