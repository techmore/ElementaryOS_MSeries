# Unified native T3 panel (retired)

**2026-10-27:** retired. T3 has one presence, its Dock launcher and window (see
[dock-taskbar](../dock-taskbar/README.md)). Remove an installed module with
`sudo bash mseries/install-t3-wingpanel.sh --uninstall` (then the panel reloads at the next login, or
restart it). The notes below are kept for history.


One GTK 4 / Granite 7 Wingpanel module replaces the standalone CodexBar,
RepoBar and T3 indicators. It embeds the **same** maintained menu used by the
dock: Usage, T3 server and GitHub, with Activity (Shiplog), Fleet and Open T3.
Machine Lab remains the local machine app and has replaced Orchard. Fleet's
remote aliases remain unconfigured at the owner's preference; no real SSH
validation is claimed. Chat validation remains deferred.

`TaskbarT3RPopover` supports either dock-owned popover or Wingpanel-hosted
content. The native host owns focus, Escape and outside dismissal. Embedded
views are lazy and stop polling on close/unmap. T3's attention/running badge
requires a recent, connected, non-stale feed and live application bus owner;
a one-shot expiry clears an idle badge without polling collectors. One normal
RepoBar object retains the existing background notification/settings behavior;
the visible embedded GitHub view never duplicates notifications. CodexBar's
v0.78.0 custom collectors, accounts, sessions, wrappers and daemon stay in use.

## Build and stage

```sh
meson setup /tmp/t3-panel-build mseries/t3-wingpanel --prefix=/usr
ninja -C /tmp/t3-panel-build
bash mseries/t3-wingpanel/test.sh /tmp/t3-panel-build /tmp/t3-panel-receipts
bash mseries/install-t3-wingpanel.sh
```

The installer runs isolated light/dark fixtures before staging in sibling
`mseries-pending-indicators/`, **outside** Wingpanel discovery. Wingpanel watches
new files and even tries loading `.so.new`; never stage a first migration inside
its directory. Staging alone does not activate on login. Explicitly run
`bash mseries/install-t3-wingpanel.sh --activate` when the owner authorizes a
reload, or run installed `mseries-activate-t3-panel` for a Debian build. Activation
stops `pantheon-wingpanel.service`, moves `libcodexbar.so`, `librepobar.so` and
`libclaude-pantheon.so` to sibling `mseries-retired-indicators/`, installs the
staged module, and starts the panel. Never load both sets together: their reused
widget GTypes and exported constructor names intentionally match. Default staging
never stops/starts the panel. The separate activation command is explicit.

Supported CodexBar/RepoBar deploys update the rollback copy while the unified
module is selected. Their full installers skip standalone module installation;
uninstalling a standalone view preserves shared settings/helpers/icons. The old
T3 installer redirects here. T3 Debian packages build this module, ship native
settings/provider marks and stage outside discovery; the explicit activation command retires the three legacy modules.
Usage still requires the separately maintained custom CodexBar backend install.
An app-only package (`CLAUDE_PANTHEON_SKIP_INDICATOR=1`) does not migrate panels.

`--uninstall` removes the unified active/staged modules and retains helper/configuration
and rollback files. It does not silently restore old indicators. To roll back,
remove the unified module and explicitly restore the desired old module(s)
from the sibling backup directory before the next panel process starts.

Tests use private HOME, buses without activation, inert collectors and desktop
actions. They cover hosted widget ownership, unopened usage, tab changes,
live/stale badge updates, six seconds without closed-view snapshot calls,
Activity/Fleet/Open T3 routing and host close signals, plus one exported module
entrypoint and legacy deployment target selection. Screenshots cover both
schemes. These do not establish a real Wingpanel load, physical focus/keyboard
acceptance, real remote connections or whole-chat parity. Strings currently
follow the shared menu's existing untranslated source; localization is open.

## First live migration defect

The first installer incorrectly assumed adding a new module was passive. At
09:19:03 on October 26, Wingpanel hot-loaded `libmseries-t3.so.new` alongside the
legacy T3 module and crashed through the old exported `dock_taskbar_t3_rpopover`
constructor ABI. Its `Restart=on-failure` service recovered at 09:19:05, after
legacy files had been retired; process maps now show only the unified module.
No explicit restart was issued, but the staging caused an unwanted automatic
restart. The corrected installer/package always stage outside discovery and
include a regression asserting the installed module destination. Live physical
menu acceptance is still open; source/build and mapped-module evidence do not
establish it.
