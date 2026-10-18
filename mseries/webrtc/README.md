# Screen Share for ElementaryOS M-series

Phone remote desktop, view-only links for friends, and local screen recording of
**the existing desktop**. The application is part of this repository, its
installed-system setup, and the ARM64 factory overlay. It uses the browser's
WebRTC engine, the desktop screen-capture portal, and a small Mutter 50 input
adapter. It does not launch a replacement desktop or modify audio/boot drivers.

## Prepared deployment continuation — 2026-10-17

The owner chose to prepare now and boot ElementaryOS later. The updated source
includes `mseries-webrtc-check` (read-only desktop/portal/lock/HTTPS checks) and
`mseries-webrtc-configure` (configure the user service and strict-host outbound
SSH tunnel from the private prepared environment). Neither starts capture or
input. They ship in the factory image and the installed-user setup.

A reviewed gateway helper is in `deploy/gateway.py`. Unprivileged `prepare`
captures the live Caddyfile and both explicitly reviewed root-owned imports,
retains their live import behavior, and expands an immutable copy for Caddy
adaptation/validation. `apply` requires isolated Python, sudo, the exact reviewed
request digest and a helper executed from pinned captured bytes. It verifies
live file identities, writes a root-private recovery copy, validates as Caddy's
own user, and restarts the existing Caddy service once with `admin off` retained.
Failed activation attempts restore the old configuration only when no concurrent
administrator edit intervened. Tests cover rollback, drift and edit preservation;
actual privileged activation remains unperformed.

The current private candidate is on SER8 at
`/home/sdolbec/mseries-webrtc-review-20261017/activation/gateway-lwxiq5sj`.
The handoff retains helper/request/candidate hashes. Do not run a mutable loader
file under sudo: the prepared activation command embeds the reviewed
`activate-reviewed.py` source with `python3 -I -c` and pins the helper bytes.
If any reviewed input has changed, preparation/inspection must be repeated.
A Caddy restart interrupts its existing sites briefly; successful service
activation still needs independent public HTTPS checks.

After booting Linux and installing this branch's feature:

```sh
# Copy only the prepared settings, not a private SSH key, from trusted SER8.
mkdir -p ~/.config/mseries-webrtc
scp -o StrictHostKeyChecking=yes \
  sdolbec@100.127.99.74:/home/sdolbec/mseries-webrtc-review-20261017/activation/gateway-lwxiq5sj/desktop.environment \
  ~/.config/mseries-webrtc/prepared.environment
chmod 600 ~/.config/mseries-webrtc/prepared.environment
mseries-webrtc-configure --environment ~/.config/mseries-webrtc/prepared.environment
mseries-webrtc-check
mseries-webrtc-open
```

The configure command defaults to the existing operator's saved SSH profile/key;
it verifies strict-host, noninteractive authentication before changing files.
Override `--ssh-target` and `--identity` to use a dedicated restricted forwarding
account/key if provisioned. No key is created or copied automatically. SER8's
existing operator route passed a temporary loopback reverse-forward health
check. A temporary Caddy process also verified the actual random-path asset,
API and authenticated WebSocket routes, unchanged fallback and revocation.
Both test listeners were stopped; no production configuration was changed.
TURN, public TLS, physical phone/input, lock behavior and real portal capture
remain live acceptance requirements.

## Install and use

On an existing ElementaryOS installation, as the desktop user:

```sh
bash mseries/post-install.sh --only webrtc
# Or: bash mseries/install-webrtc.sh
```

In the factory image, **Screen Share** is already in the application launcher.
The image build installs the locked runtime, launcher, user service and Python
input adapter. Launching it starts a loopback-only user service; it does not
start capture. The transform also carries a **Set Up Screen Sharing** launcher.

1. Open **Screen Share**, then **Share my screen**. Approve a screen/window in
   the browser's picker. Keep the host page open and the desktop logged in.
2. For friends, copy the **Friends · view only** link.
3. For your phone, enable **Allow phone control on this desktop**, then copy
   the separate private phone link. Swipe the touchpad to move the pointer,
   tap/click, scroll, or send text. Desktop keyboards work while the touchpad
   has focus; Ctrl/Alt/Shift/Super chords are sent atomically.
4. **Start recording** works on the host or receiver. **Stop recording**, then
   **Save recording**. Output stays in that browser, capped near 256 MiB (the
   final encoder chunk may exceed that cap). Save before closing the page.
5. **Stop sharing**, close the host tab, or use the browser's stop-capture
   action to revoke every link and disable control.

Use a current desktop Chromium/Brave or Firefox for the host. Phone browsers
receive video; they do not need a native app. iOS/Safari, real portal capture,
real screen audio and physical phone input still need target qualification.
Audio can only be captured when the browser/portal offers it; the request is
optional and does not restart or reconfigure PipeWire.

## One address for LAN and internet

A phone on the same subnet can receive WebRTC media directly. It still needs a
reachable **HTTPS** page/signaling service. Bare `http://192.168…` cannot serve
as the screen-capture origin. Do not expose the Node listener directly.

Recommended deployment: keep the Node service on the ElementaryOS desktop at
`127.0.0.1:8789`, make an **outbound SSH reverse tunnel** to SER8 loopback port
`18789`, and serve it through SER8's existing Caddy HTTPS gateway. Both the
local host page and public HTTPS origin attach to that same service. Video is
peer-to-peer when ICE can connect; Caddy/SSH carries signaling and input, not
the WebRTC media. `MSERIES_WEBRTC_PUBLIC_URL` makes the locally opened host page generate
usable public invitations.

Verified on 2026-10-17: SER8's historical LAN SSH address timed out, but strict
host-key SSH at its saved Tailscale address worked. The live Caddy site names
include `stoverparc.org`, Tasks, Homeboard, Swartzit, Sonder, Energy and Daedalus.
There is no `remote.stoverparc.com` site in that inspected config, and neither
`remote.stoverparc.com` nor `remote.stoverparc.org` resolved from this Mac.
TM-Remote's own deployment files use **mdm.stoverparc.org**, which is also the
owner's selected gateway for this feature. Use a separate **random path** on
that site. Preserve all TM-Remote routes. A direct HTTPS probe on 2026-10-17
resolved the mdm name but failed the TLS handshake; the gateway handoff also
records unfinished activation. Its TLS/ingress and existing upstream route must
be restored/verified before claiming a working public share.

On the ElementaryOS desktop:

```sh
mkdir -p ~/.config/mseries-webrtc
cp mseries/webrtc/deploy/environment.example ~/.config/mseries-webrtc/environment
chmod 600 ~/.config/mseries-webrtc/environment
# Edit exact origin, STUN and optional TURN settings before restarting.
systemctl --user restart mseries-webrtc.service
```

Provision a dedicated SER8 SSH account/key. Its authorized_keys entry should
restrict the key to remote forwarding only:

```text
restrict,port-forwarding,permitlisten="127.0.0.1:18789" ssh-ed25519 YOUR_DESKTOP_PUBLIC_KEY
```

The server's sshd Match block should use `AllowTcpForwarding remote`,
`PermitListen 127.0.0.1:18789`, `GatewayPorts no`, `PermitTTY no`, and
`MaxSessions 0` for that dedicated account. Do not apply these settings to the
existing operator account. Pin SER8's SSH host key through an already trusted
route. Update the tunnel unit's target to your reachable verified SSH host
(alias or Tailscale address); no password or private key belongs in Git.

```sh
cp mseries/webrtc/deploy/mseries-webrtc-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mseries-webrtc-tunnel.service
```

Choose a random routing prefix (`openssl rand -hex 24`) and replace
`REPLACE_WITH_RANDOM_PREFIX` in the environment and Caddy snippet with the same
value. Example shape: `https://mdm.stoverparc.org/<random-prefix>/#join=<random-capability>`.
The routing prefix does not replace participant authentication.

On SER8, insert `deploy/Caddyfile`'s **handle_path block inside the existing
mdm site** and wrap its existing fallback directives in `handle { ... }` so
TM-Remote and screen-sharing routing are exclusive. Do not add a duplicate mdm
site or replace its existing routes. Caddy strips the random prefix before
proxying, while relative browser URLs retain that prefix. Preserve its ingress
bind/TLS policy, imported routes and other sites. The inspected SER8 uses a
WireGuard/LAN gateway layout; first complete the existing mdm gateway activation
and validate the complete merged config before reloading Caddy.
Administrative write/reload was unavailable to this session; no live proxy
configuration was changed.

A TURN relay is necessary for dependable connections across restrictive NATs.
`deploy/turnserver.conf.example` is a coturn template, not an active/open relay.
Provision public relay DNS/IP and UDP/TCP 3478 plus the limited UDP relay range;
HTTP tunnels alone cannot relay this traffic. Set a private shared secret in
coturn and `TURN_SECRET`; set `TURN_URL` in the application's environment.
Only authenticated participants receive one-hour HMAC credentials. Sessions
expire after four hours, so reconnect with a fresh invite/ICE credential if a
network change requires new allocations after an hour. STUN is explicit and
optional; the example uses Cloudflare. Without TURN, cross-network success is
not promised. Shared NAT public IPs can make relay-to-relay routing sensitive
to firewall policy; qualify from cellular as well as the LAN.

## Access and lifecycle

- Host key: 256 random bits, user-owned `~/.config/mseries-webrtc/owner.key`,
  mode 600. The launcher passes it as a URL fragment, the page removes it from
  browser history, then authenticates over the same origin. Never share it.
- Invite capabilities: separate random viewer/controller tokens, URL fragments,
  at most four viewers plus one controller; no tokens in request URLs/logs.
  Anyone possessing a link has its role until stop/expiry; friends can record.
- Signaling validates the configured exact origin. Viewer input and host
  operations are refused on the server, regardless of client UI changes.
- Phone control is off until the host enables it. The input subprocess exists
  only then; no remote shell, sudo, input device permissions or exposed local
  input API is used. It checks logind lock/active state before each operation
  and while idle, and fails closed when lock/session/backend checks fail.
  Actual Gala/logind behavior remains a hardware acceptance gate.
- Only relative pointer input, atomic clicks/chords and bounded text are
  implemented. No drag-and-drop, clipboard sync, file transfer, wake/unlock,
  login-screen control or unattended capture. Keep a session sharing before
  leaving if you want access from your phone. A disconnected phone disables
  control until the host enables it again. A lost connection needs a fresh
  page/invite; automatic reconnect is not implemented.
- Five peers mean five video sends. The initial profile is 15 fps with a
  3 Mbit/s ceiling per video sender; actual browser adaptation, CPU use and
  battery cost must be measured on M1 Pro. No hardware encode claim is made.

The Mutter RemoteDesktop interface is private/version-dependent. The adapter
uses the **50.1** XML's boolean button/key state and relative-pointer methods:
https://github.com/GNOME/mutter/blob/50.1/data/dbus-interfaces/org.gnome.Mutter.RemoteDesktop.xml
Unsupported versions, missing `python3-gi`, unavailable session or lock state
leave screen viewing/recording usable but phone control disabled.

## Validation and removal

```sh
npm ci --prefix mseries/webrtc --ignore-scripts --no-audit --no-fund
npm test --prefix mseries/webrtc
python3 -m unittest discover -s mseries/webrtc/test -p 'test_*.py'
bash mseries/webrtc/install.sh --dry-run
```

The dedicated CI also checks image dependency wiring and overlay pruning on
Linux. Browser acceptance uses a synthetic moving canvas over a real local
peer connection, including receiving video at a phone-sized viewport and
saving a MediaRecorder file. This is not proof of a real Pantheon screen or
physical phone, LAN/cellular/TURN, lock behavior, ARM64 image boot, or installed
service recovery; those remain explicit target acceptance tasks.

For a user installation: `bash mseries/install-webrtc.sh --uninstall`. The
factory copy is part of immutable `/usr`; stop its user service to disable it.
Stop/disable the optional tunnel separately. Removing the private config
revokes the owner key (regenerated next launch). No installer changes the
bootloader, kernel, audio stack or global firewall.

## Discovery and attribution

The ten most recently pushed Techmore repositories had 41 branches (30 excluding
dependency update branches); none was named for WebRTC. The separate machine's
`mtg-board-layout` working tree contains unpublished WebRTC video-table work
(`useTableMedia.ts`, `tableMediaSenders.ts`, `docs/ONLINE-PLAY.md`). Its remote
branch is `codex/default-expanded-hand` at
`bf9ae5af5632d530a77f983f660c8e687defcf8a`; those files were untracked locally,
so they must not be described as a published reusable branch. No game code,
credentials or unrelated local changes were imported. This implementation is
new and uses native browser APIs plus the `ws` **8.22.0** dependency, pinned
with an npm integrity lock. Preserve `node_modules/ws/LICENSE` (MIT) when
redistributing. The factory build installs that notice alongside this guide.
Selkies 2.0 was considered, but its Wayland mode starts a separate/headless
desktop; that does not meet the existing Pantheon-session requirement.
