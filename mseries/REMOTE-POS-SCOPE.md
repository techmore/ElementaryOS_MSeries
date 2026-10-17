# Remote desktop, POS support and no-MDM businesses: draft scope

Status: **draft for owner review, 2026-10-16. Nothing here is implemented.**
Target repos: `techmore/tm-remote` (control plane), `techmore/rupert`
(Shopify/Square inventory sync), this repo (Pantheon image and agent host).
Out of scope, permanently: healthcare / medical customers.

## Context established so far

- tm-remote is a Go control plane with outbound agents, a SwiftUI macOS app and
  a web UI. It already has an Apple MDM listener (Apple TV only), VNC/RDP
  launch, audit history and policies (`docs/MDM-ROADMAP.md`,
  `docs/REMOTE-DESKTOP-ROADMAP.md`, `docs/PUBLIC-CONTROL-PLANE.md`).
- Target customers are small businesses that do **not** run MDM. An MDM-first
  design cannot be the foundation for them.
- Rupert syncs Shopify and Square. The goal is to move from CTraxs to Rupert.
  What CTraxs does and where its data lives is **not yet known**.
- POS hardware includes a first-generation Square device and iPads with a
  display attachment. The exact model is **not yet known**.
- Processors wanted besides Square: PayPal and Authorize.net.

## Customer profile (owner, 2026-10-16)

Small shops with roughly 10 computers each, mixed and unmanaged, **no
firewall**, and a Square-style POS. No IT staff, no MDM. This is the design
center: onboarding must be a single install step per machine, and the product
has to improve the shop's security baseline, not just reach the machines.

Implications:
- **Agent-first, outbound only.** Nothing inbound, so no port forwarding and
  no firewall changes are needed to manage a shop.
- **Network baseline.** With no firewall, offer a recommended gateway
  (for example a small OPNsense/pfSense or an OpenWrt box) and a VLAN split:
  POS and card readers on their own segment, office machines separate, guest
  Wi-Fi separate. This is likely the biggest PCI-scope reducer for these
  shops, ahead of anything on the desktops.
- **Discovery.** tm-remote already scans with Bonjour/mDNS and Nmap-style
  checks; use it to inventory what is on a shop's LAN before enrolling.
- **Host hygiene checks** reported per machine: OS updates, disk
  encryption, local firewall state, open listening ports, default or shared
  accounts. Report first; remediate only after confirmation.
- **Multi-tenant.** Each shop is a separate tenant with its own enrollment
  tokens and audit trail, which depends on issue 8 below.

## Rupert rollup: the information system (owner, 2026-10-16)

Rupert becomes the system of record and the one place a shop owner looks.
Everything else is a swappable backend behind it.

- **Canonical model in Rupert:** shops, locations, products/variants,
  inventory levels, orders, customers, payments (tokens and IDs only),
  devices, support sessions. Every external record is linked by a
  `(provider, external_id)` mapping table, so switching a provider re-points
  mappings and does not rewrite history.
- **Ports and adapters** (Rails service objects with a shared contract test
  suite, one adapter per provider):
  - commerce/catalog/inventory: Shopify, Square, CTraxs importer, CSV.
  - payments: Square, PayPal, Authorize.net.
  - device management and remote support: tm-remote, called over its API as a
    separate service (not merged; see `PUBLIC-CONTROL-PLANE.md` for why).
- **Per-shop configuration** chooses the active adapter for each port.
- **Easy switching:** run the new adapter in shadow mode (read-only, compare
  results), then cut over per shop with a recorded rollback. An adapter that
  fails the contract suite cannot be selected.
- **CTraxs** is just a source adapter used for the migration import.
- **Dashboard:** one view per shop of sync health, device health, open
  support sessions and processor status.

Open design questions: single-tenant per shop deployment or one multi-tenant
Rupert; how Rupert authenticates to tm-remote (per-shop scoped tokens, which
needs issue 8); and which ports are v1 versus later.

## Issues and proposed resolutions

### 1. MDM hosting does not work for the intended customers
- **Known:** the owner reports the tm-remote MDM server "sucks and does not
  work" when hosted for outside businesses (for example on DigitalOcean).
- **Unknown:** the actual failure. Candidates to check, none confirmed:
  APNs push certificate and its Apple-signed CSR, MDM vendor/signing
  requirements, TLS and identity-certificate pinning behind a proxy, the
  separate MDM TLS port, DHCP/NAT, and Apple Business/School Manager
  enrollment.
- **Resolution:** capture the real error first (logs, `/api/health/detail`,
  device enrollment failure text). Then decide whether to keep MDM only as an
  optional, supervised-device feature. Do not make it a prerequisite.

### 2. Businesses without MDM need an agent-first path
- **Resolution:** outbound agent on Linux/macOS/Windows desktops; for iPads,
  a one-time Apple Configurator or manual setup (Guided Access / single-app
  mode) documented as a checklist, plus Square's own dashboard tools. Verify
  what Square's dashboard device management offers before duplicating it.

### 3. Remote desktop including the login screen and reboot
- **Resolution:** root systemd agent starting after `tailscaled`, with a
  greeter capture backend (LightDM greeter) and a user-session backend
  (PipeWire), handing over via logind. WebRTC H.264 for media, DataChannel for
  input, signaling over the agent's existing outbound connection.
- **Verified on the Asahi test machine:** LightDM and `tailscaled` run as
  system services; current session is Wayland with Gala. The greeter's display
  server (X11 or Wayland) is **not yet determined**.
- Disk-encryption unlock before boot is out of scope (needs an initramfs
  feature; do not touch bootloader/initramfs as part of this).

### 4. Network layer
- Bundle the Tailscale client, or use Headscale (self-hosted control server)
  or NetBird/WireGuard. Record source revisions, keep licenses and
  attribution. Decision pending.

### 5. Payments and PCI scope
- Processor-adapter interface in Rupert (Square, PayPal, Authorize.net).
- Keep card data out of our systems: P2PE readers for card-present, hosted
  fields/redirect for online. Store only tokens, transaction IDs, last four.
- Remote sessions: view-only by default, no frame recording, visible
  indicator, audit of both ends, time-boxed elevated control, MFA for
  operators. Wording in docs must be "intended to reduce PCI scope", never
  "compliant".

### 6. Square / iPad POS devices
- iOS allows no third-party remote control. Manage through the Square and
  Shopify APIs (catalog, inventory, orders, webhooks), not the screen.
- Optional view-only support via AirPlay mirroring to a receiver (for example
  UxPlay) feeding the same viewer. Experimental.

### 7. CTraxs to Rupert migration
- Blocked on: what CTraxs holds, export format, which stores depend on it.
- Resolution when known: map CTraxs data to Rupert's import path, run both in
  parallel, cut over per store, keep a rollback.

### 8. Control-plane gaps already recorded in tm-remote docs
- Single shared bearer token; audit actor is always `control-plane`.
- No rate limiting; cannot push a new server URL to agents.
  These block exposing the control plane to other businesses and must be fixed
  before any multi-customer hosting.

## Questions for the owner

1. What exactly fails with the hosted MDM (error text, which step)?
2. What does CTraxs do, and what are its export options?
3. Exact Square hardware model and the iPad model/OS.
4. Primary processor, and is card-present needed?
5. Should I file these as GitHub issues in `techmore/tm-remote` and
   `techmore/rupert`, or keep them in docs only?
