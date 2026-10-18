# Orchard for Incus

A native elementary OS manager written in Vala with GTK4 and Granite 7,
inspired by [Orchard](https://github.com/andrew-waters/orchard). It uses the local
Incus Unix socket and includes an optional persistent Wingpanel indicator.

The [upstream comparison](docs/UPSTREAM-PARITY.md) reviews 131 capability rows
against Orchard revision `2c78257c8602ffed61f383ee6e737bfc37b142ee`: 54 implemented,
38 native adaptations, 37 documented runtime/platform incompatibilities and two
Incus-specific additions. Adaptations describe the differences explicitly; this
is not a claim of identical behavior or complete manual UI verification.
The CSV, source-view inventory and service-symbol index accompany the report.

## Features

- Containers and VMs: create from simplestreams or a cached image, CPU/memory
  limits, environment and labels, ephemeral instances, start/stop/restart,
  pause/resume, console/shell, confirmed deletion and bulk actions.
- Inspect and edit native configuration with ETag conflict protection, optional
  stop/apply/start, JSON-quoted multiline values, snapshots, restore, clone and
  streamed native backup export. Running ephemeral instances cannot use the
  stop/apply/start workflow because stopping would delete them.
- Dashboard and instance statistics: CPU, memory, network and root disk,
  timestamped history up to 24 hours, saved sort/group settings, cached image
  sizes and storage-pool accounting. Missing counters and discontinuities are
  shown explicitly rather than treated as zero usage.
- Images, bridges, DNS zones, pools, profiles, projects and operations: native
  inventory and inspection, supported resource settings and creation/removal,
  image download progress/cancellation and launch. Project context switching
  and custom storage-volume CRUD remain separate Incus extensions.
- Folder mounts, port proxies and network interfaces with version-checked
  device updates. Mount inventory distinguishes local and inherited devices;
  removing a mount does not delete its host directory.
- Independent log viewers: bounded runtime/console tails, journal snapshots,
  filtering, highlighting and coordinated panes. Guest journals require
  `journalctl`; the app reports images that do not provide it.
- OpenAI-compatible local model endpoint bookmarks, model discovery and chat,
  enabled-server selection and optional API keys in Secret Service. Existing
  Ollama/LM Studio/compatible servers must be installed and running separately.
- Native model sandboxes: create a system container or VM with explicit root
  storage/NIC, resource limits and no inherited profile mounts; inspect current
  network policy, attach model endpoint environment, chat/shell and immediate
  stop. The host-only option requires a managed bridge with routing/NAT and IPv6
  disabled and its DNS listener disabled. It describes observed configuration,
  not a security guarantee. Host services must listen on the chosen bridge
  gateway; desktop API keys are never injected into guests.
- Ctrl+K command palette, fuzzy search, `orchard:` navigation links, preferences,
  server diagnostics and explicitly confirmed host daemon controls.
- Wingpanel tree icon and running-instance badge (including zero). CPU/memory
  graphs, instance start/stop and manager launcher stay in the popover. A dash
  indicates an unavailable daemon; the indicator stays visible in the session
  and is excluded from the greeter.

## Runtime scope

The verified target is **Incus 6.0.5** on aarch64 elementary OS. OCI application
containers arrived in Incus 6.3, so the current OCI limitations are version- and
implementation-specific. This work does not upgrade Incus or install another
engine. Dockerfiles/BuildKit, Compose, Apple's container/Kubernetes plugins,
macOS MLX runtime supervision, Apple signing/updating and host DNS-resolver
integration are documented as incompatible with this target. Native system
images and externally managed compatible model servers provide the stated
counterparts. See the comparison before assuming upstream semantics.

## Build and install

Requires Vala, Meson/Ninja, GTK4, Granite 7, libsoup 3, JSON-GLib, libsecret and
GIO Unix development packages. Socket access requires the appropriate local
Incus administration group; it grants powerful host access. `incus` and a
supported terminal are required for guest interactive shells/consoles.

```bash
meson setup build --prefix=/usr -Dwingpanel=enabled
meson compile -C build
meson test -C build --print-errorlogs
sudo meson install -C build
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor
sudo update-desktop-database /usr/share/applications
INCUS_SOCKET=/var/lib/incus/unix.socket ./build/com.github.techmore.orchard-incus
```

Wingpanel 9 is optional: use `-Dwingpanel=disabled` for other desktops or
`-Dwingpanel=enabled` to require it. Its module installs in the dependency's
`indicatorsdir`. Log out and back in after replacing a loaded module. Closing
the manager leaves the panel companion running.

Preferences live under `$XDG_CONFIG_HOME/orchard-incus`, metric history under
`$XDG_STATE_HOME/orchard-incus/metrics`; the defaults are `~/.config` and
`~/.local/state`. `INCUS_SOCKET` overrides the saved socket preference. API keys
use Secret Service, not preferences files. `orchard:` links require registering
the installed desktop entry as the scheme handler.

## Verification

Five automated suites use disposable sockets/HTTP endpoints and isolated
configuration/state. They exercise lifecycle JSON, concurrent-edit conflicts,
restart ETag changes, multiline configuration, native exports, model/auth
responses, bridge-policy checks, panel error/recovery and construction of the
native windows. GTK tests require a desktop display and otherwise skip.

Live tests used owned temporary containers, a new temporary bridge and a native
Alpine VM. Container lifecycle/snapshots/mount/config/export, host-service access
with cross-network routing blocked, and VM boot/agent/environment passed. Test
instances and networks were cleaned up. Existing Rupert and orchard-test
instances were preserved. The report distinguishes these checks from untested
manual UI flows, real model generation/keyring storage and privileged daemon
controls. See `NOTICE.md` for upstream attribution.
