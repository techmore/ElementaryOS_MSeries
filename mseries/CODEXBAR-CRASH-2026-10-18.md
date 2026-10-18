# Wingpanel popup lifetime investigation — 2026-10-18

The 14:03:09 crash was real: Wingpanel PID 233125 exited with SIGSEGV and recovered
as PID 248867. The CodexBar daemon stayed running. Debugging used the saved core,
never an attachment to the live panel or an account switch.

## Evidence

Matching GTK 4.22.4 debug symbols identify the failing stack:

```
_gdk_display_pause_events (display=NULL)
gdk_surface_flush_events
_gdk_frame_clock_emit_flush_events
gdk_frame_clock_flush_idle
```

The surface in that callback had reference count zero, `destroyed=1`, and a NULL
display. Earlier journal warnings reported an indicator being finalized with a
`GtkPopover` still parented to it, followed by accessibility/widget assertions.
The core does not identify which indicator owned that popup or the exact action
that removed its anchor. Rewriting identical icons coincided with the warnings;
avoiding that invalidation remains useful but does not repair widget ownership.

## Reproduced defect and repair

Our public Wingpanel source is pinned to
[elementary/wingpanel 6b8ae0453b1fd6dc07bd246642998011f04b2125](https://github.com/elementary/wingpanel/tree/6b8ae0453b1fd6dc07bd246642998011f04b2125).
Its `PopoverManager.current_indicator` can be the last strong reference to a
removed indicator entry. The switch branch releases that reference before
unparenting its popup; the close branch can leave the popup attached during its
closing animation. An isolated test using the pinned production classes reproduces
the matching finalization/accessibility warnings when it removes the open anchor,
releases its other reference, then switches or closes the menu.

`patches/wingpanel-popover-lifetime.patch` retains the previous entry through
popup detachment and explicitly detaches on close before that reference expires.
The full-height/notch and right-clock patches still apply. The source and existing
copyright/license headers remain upstream GPL-2.0-or-later; only a patch is vendored.

Run the regression without touching the real panel:

```sh
bash mseries/wingpanel-tests/run-popover-lifetime.sh
# Optional existing checkout of exactly the pinned revision:
bash mseries/wingpanel-tests/run-popover-lifetime.sh /path/to/wingpanel
# Negative control, expected to fail:
bash mseries/wingpanel-tests/run-popover-lifetime.sh /path/to/wingpanel --unpatched
bash mseries/install-wingpanel-codexbar-left.sh --build-only
```

The fixture uses fake indicators, an isolated non-activating D-Bus, private HOME,
and Xvfb. Switch/close with animations disabled/enabled all pass with the patch;
the original fails with the matching invalid-widget critical. Criticals are fatal
from the anchor-removal phase onwards. The minimal fake host produces an unrelated
initial-popup ancestry critical on this GTK build before that phase; this test does
not claim to validate that setup path or all GTK popup behavior. The full patched
Wingpanel build passes its available Meson checks (upstream defines no unit tests).
The 13 CodexBar native targets and full v0.77.0 port/schema check also pass.

This fixes a concrete, reproduced lifetime defect consistent with the saved crash.
It does not prove that every possible GTK crash has been eliminated. Live activation
and observation are recorded in OS9-HANDOFF.md.

A separate startup warning remains: `IndicatorBar.update_flow_box_max_children`
passes zero to GTK when its model becomes empty. GTK rejects that value; no new
panel coredump or subsequent popup/accessibility warning was observed during the
activation check. This is recorded separately from the repaired popup lifetime bug.
