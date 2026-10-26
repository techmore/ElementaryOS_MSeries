# Wingpanel indicator

The at-a-glance view of the T3 server on the panel. T3 Code itself has no desktop tray or menubar
indicator (only a phone widget), so this is the only one.

- **Panel:** the app's symbolic icon with a badge: the number of pending permission prompts, or a dot
  while a thread runs (the icon turns into a question mark when something needs you).
- **Popover:** the same native Tokens/Accounts/Activity content used by the Dock.
  Tokens includes Claude, Codex, Grok, OpenCode and other reported providers.
  Accounts separates saved computer-local identities from all enabled T3 server
  instances. Unknown and stale data are not zero/live capacity; expired resets
  require refresh. Both surfaces compile `mseries/dock-taskbar/TaskbarT3RPopover.vala`
  rather than maintaining separate selected-provider renderers.

![indicator](../docs/screenshot-indicator.png)

It watches `~/.cache/claude-pantheon-rs/status.json` (schemaVersion 1) for server
accounts, provider history and activity. Saved local account helpers run on open
or explicit refresh. Neither surface opens a second T3 connection, switches an
account or invents quota when a provider/API is unavailable.

## Build, test, install

```sh
./install.sh              # meson build, headless probe, sudo install; the panel loads it at next login
./install.sh --restart    # the same and restart Wingpanel now (only when the owner asks)
./install.sh --uninstall
bash mseries/install-claude-pantheon-indicator.sh   # from the repo root, installs the build deps first
```

Wingpanel 8/9 loads indicators only from `pkg-config --variable=indicatorsdir wingpanel-9`
(`/usr/lib/aarch64-linux-gnu/wingpanel-9` here); there is no per-user indicator directory, so the
copy needs sudo. Build requirements: `meson ninja-build valac libwingpanel-dev libgranite-7-dev
libjson-glib-dev libgee-0.8-dev`.

The fixture probe checks that distinct Claude, Grok and OpenCode token totals and
account rows survive rendering alongside the prompt badge. `PROBE_SHOT=<png>`
captures the shared view under Xvfb. Isolate `XDG_RUNTIME_DIR` when starting a
private D-Bus session so probe services cannot replace live accessibility sockets.
