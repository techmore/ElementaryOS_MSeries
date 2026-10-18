# Horizon-hosted desktops over native RDP (arm64)

Omnissa Horizon Client is closed source and has no public arm64 Linux build, so this machine cannot run it natively.
`mseries/install-horizon-rdp.sh` installs Ubuntu's FreeRDP 3 (native arm64, SDL3 client for Wayland, xfreerdp for X11) and a small launcher.

    bash mseries/install-horizon-rdp.sh              # install
    horizon-rdp [--x11] HOST [USER] [DOMAIN]          # connect; password is prompted
    bash mseries/install-horizon-rdp.sh --uninstall   # remove launcher (keeps FreeRDP)

Also available as "Horizon RDP" in the app launcher.

## What this covers
- Direct RDP (TCP/UDP 3389) to a Windows or Linux desktop whose RDP is enabled and reachable from here (VPN or
  internal network). Clipboard, audio, microphone, dynamic resolution and H.264 (AVC444) are on by default.
  Certificates use trust-on-first-use.

## What it does not cover
- Horizon's Connection Server broker, the Blast Extreme protocol, USB redirection and Horizon-specific features.
  Pools that only allow Blast, or admin policy that blocks direct RDP, will not work here. Ask the Horizon admin
  whether RDP is allowed to the target desktop, or use the browser-based HTML Access if the deployment offers it.
- Not tested against a real Horizon deployment; only the install and launcher were checked locally (FreeRDP
  3.32.1 from Ubuntu resolute-updates).
