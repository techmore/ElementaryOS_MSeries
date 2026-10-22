# Snapped windows covered newer windows — 2026-10-21

**Symptom (owner):** with a window snapped, other windows "can't register over it", and the Touch ID sheet (a dialog opened
over a snapped Settings window) did nothing and could not be dragged.

**Cause:** the compositor re-applies tiles, work-area limits and window modes by calling Smithay's `Space::map_element(window,
location, false)` on windows that are already mapped. Its documentation says it "map[s] a SpaceElement and move[s] it to top of the
stack", so every reconfigure (for example when a bottom panel shows or hides, via `reconfigure_managed_windows` →
`reconfigure_tiled_windows`) lifted every snapped window above all newer windows, including dialogs opened over them. A dialog
behind its parent is unreachable, so it cannot be clicked or dragged.

**Fix:** `place_in_space` / `PantheonCompositor::place_window` (`src/state.rs`) use `Space::relocate_element`, which changes a
window's location without touching its stacking, and map an unmapped window on top. Applied where an existing window is only
being moved or resized: `tiling.rs` (tile and move-to-output), `pantheon_shell.rs` (window mode, panel clearance),
`xwayland.rs` (X11 configure and mode), and the off-screen recovery in `state.rs`. Left as `map_element` on purpose: first
mapping, workspace restore (which maps in order and raises the last), the overview restore, and panel layering.

**Verified:** four unit tests with a stand-in element: `map_element` does reorder (the premise), a snapped window stays under a newer
dialog after its tile is re-applied, location updates keep every stack position, an unmapped element is mapped on top; the
whole suite passes (48). **Not verified:** on the live desktop. Nothing is deployed: the installed compositor is unchanged until
`mseries/install-pantheon-rust-compositor.sh` is run and the session restarted.
