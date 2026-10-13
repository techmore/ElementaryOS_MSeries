# DRAFT: not filed. Review before posting to https://github.com/elementary/wingpanel/issues

## Title
Wingpanel segfaults in `PanelWindow.on_realize` (`wl_proxy_get_version`) on elementary OS 9 arm64

## Summary
`io.elementary.wingpanel` intermittently dies with SIGSEGV on startup, inside the `realize` handler of
`PanelWindow`. Gala respawns the panel, so the desktop recovers on its own, but the top bar vanishes for
a few seconds each time, and it can repeat several times in a row.

## Environment
- elementary OS 9 (early access), arm64, Apple M1 Pro (MacBookPro18,3), Wayland session
- `io.elementary.wingpanel` 8.0.4+r811+pkg79~daily~ubuntu9.1
- `gala` 8.6.2+r3174+pkg135~daily~ubuntu9.1 (the 2026-10-12 crashes predate our patched Gala)
- `libmutter-18-0` 50.1-0ubuntu2.4, Linux 7.1.13 (Asahi-derived)

## Backtrace (same top frames in every dump we inspected)
```
#0  wl_proxy_get_version (libwayland-client.so.0 + 0x73b0)
#1  _wingpanel_panel_window_on_realize_gtk_widget_realize (/usr/bin/io.elementary.wingpanel + 0xaad0)
#2  g_closure_invoke (libgobject-2.0.so.0)
...
#7  gtk_widget_realize (libgtk-4.so.1)
#8  gtk_widget_map (libgtk-4.so.1)
```

## Frequency
8 SIGSEGV dumps on 2026-10-12 (09:35:56, 09:36:04, 09:36:13, 09:36:21, 09:36:27, 09:49:35, 13:22:23,
15:16:23 PDT). Five fell within 31 seconds, so a respawn can crash again straight away. None on 2026-10-13.

## Where we think it happens
`on_realize` connects the surface signals and calls `init_wl ()`. `init_wl ()` binds
`io_elementary_pantheon_shell_v1` from the registry and, in `registry_handle_global`, calls
`desktop_shell.get_panel (wl_surface)` followed by `desktop_panel.set_anchor (TOP)` and `set_hide_mode (NEVER)`.
Those calls marshal on the proxies, and a NULL or already-destroyed proxy would fault in
`wl_proxy_get_version`, as seen. A plausible trigger is the panel realizing while the compositor is restarting
or has not yet advertised the shell global. This is a hypothesis from reading the source; we have not
confirmed which proxy is invalid (no debug symbols for the binary).

## Not yet ruled out
Our system also loads locally patched indicator plugins in the same process (network, Quick Settings). Their
code runs after the panel realizes, so we believe they are not involved, but we have not reproduced the crash
with stock plugins.

## What would help
A NULL check on `desktop_shell`, `wl_surface` and `desktop_panel` in `registry_handle_global`, or deferring
`init_wl ()` until the surface and shell global exist, would avoid the fault. We deliberately have not patched
this locally: a panel that survives without being anchored is arguably worse than one that Gala respawns.
