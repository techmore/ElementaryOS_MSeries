# Corners: Mac-compliant rounded edges (SDK tokens and compositor contract, 2026-10-23)

Owner direction: the "curves" are rounded edges that match the MacBook Pro: the display's own rounded corners, and windows and
controls that follow them. This defines one corner system for the SDK and the compositor. Related: the open P2 item in
[BUG-FIX-ROADMAP.md](BUG-FIX-ROADMAP.md) ("app windows do not consistently follow the rounded shape of the built-in display"),
[DESKTOP-SETUP.md](DESKTOP-SETUP.md) (the Gala screen-corner patch), [SDK-INTROSPECTION-AND-STREAMING.md](SDK-INTROSPECTION-AND-STREAMING.md).

## 1. What exists today

| Piece | State |
|---|---|
| Screen-corner mask (black rounded masks over the built-in display's four corners, above everything, external monitors left square) | A **Gala patch** (`mseries/patches/gala-screen-corners.patch`), radius 14 logical px (`GALA_SCREEN_CORNER_RADIUS`). The live session runs the **Rust compositor, which has no mask and no corner code at all** |
| Window radius | A GTK stylesheet tweak (0.5rem to 0.8rem). Covers GTK apps only; the roadmap notes it does not cover every application and that the mask rounds the display, not individual windows |
| A numeric standard | Apple's Human Interface Guidelines do not publish one mandatory radius for all windows, so the numbers below are ours, tuned by eye on this display, not copied from macOS |

## 2. The corner tokens (built, in `msdk/data/tokens.json` under `corners`)

Logical pixels, shared by SDK apps and meant to be read by the compositor:

| Token | Value | Used for |
|---|---:|---|
| `screen` | 14 | The built-in display's physical corner (the mask) |
| `window` | 12 | Floating window outline and title band |
| `popover` | 10 | Menus, popovers |
| `card` | 12 | Cards, editors, the Transcript bubbles' parent shapes |
| `bubble` | 14 | Chat bubbles |
| `control` | 8 | Buttons, entries, segmented tabs |
| `min` | 4 | The smallest radius a concentric inner corner may shrink to |
| `style` | `continuous` | Reserved: corner shape (see section 4) |

**Rules (the "concentric" rule is Apple's):** a shape inset from a rounded corner takes `outer - inset` (helper
`concentric_px(outer, inset)`, never below `min`), so inner and outer curves share a centre and the gap stays even. A window never
has a larger radius than the display (`window <= screen`; tested). Maximized and fullscreen SDK windows have radius 0 in their own
stylesheet because an app cannot know whether it is on the built-in display or a square external one; the compositor decides (below).

## 3. Compositor contract (built in the Rust compositor 2026-10-23; see section 7)

The compositor is the only layer that can make every app, including third-party and client-side-decorated windows, follow the curve.
It should read the same `corners` tokens and implement:

1. **Screen mask** on the built-in output only, radius `screen`, drawn above windows, the dock, the top bar and the lock screen.
   External outputs stay square. (Replaces the Gala patch for the Rust session.)
2. **Window clip:** every toplevel's rendered surface is clipped to a rounded rectangle of radius `window`; shadows and the focus
   outline follow the clipped shape.
3. **Hug the display:** a window whose outer corner touches a corner of the built-in display (maximized, tiled halves and quarters,
   fullscreen) uses `screen` at that corner, so it follows the display's curve; its other corners use `window` or 0 against a screen edge.
   On an external output those corners are square.
4. **Popups and dialogs:** popovers and menus clip to `popover`, dialogs to `window`.
5. **Layer surfaces** (dock, panels) round only the corners away from the screen edge, with `window`.
6. **Content stays intact:** clip only; never resize or crop client content. Surfaces that cannot be clipped cleanly (video overlays,
   some X11 windows) are listed, as the roadmap item requires.
7. **Per-output policy** from the compositor's display configuration (which output is the built-in panel), not from the apps.

## 4. Continuous corners

Apple's corners are continuous curves (a squircle: curvature eases in and out, no sudden change where the arc meets the edge), not
circular arcs. CSS `border-radius` can only draw circular arcs, so SDK stylesheets approximate with `corners.*`. The compositor's
clip shader can draw the real shape from a signed-distance function of a superellipse, which is also cheap on the GPU; `corners.style`
selects `circular` or `continuous`. This is the most visible "Mac-like" detail and costs nothing extra once a shader clips windows.

## 5. Calibration

The panel's real corner radius is not documented. Measure it once on this MacBook Pro: show a test pattern with a high-contrast border
and bring the mask radius up until the mask edge meets the glass edge with no visible gap or bite, in both light and dark; record the
number in `tokens.json` and this file. The current 14 came from eye-tuning (raised from 10 on 2026-10-1x).

## 6. Work items

1. Rust compositor: screen mask, window clip with a rounded-corner shader (Smithay GLES custom shader, as other Smithay compositors do),
   hug-the-display policy, popups, layer surfaces, per-output policy, tests for the geometry (which corners get which radius).
2. SDK: done for tokens, CSS and the concentric helper; next is an `msdk shot` check that compares a window's corner pixels to the token.
3. Calibration pass and a record of the result.
4. Qualify native GTK, libadwaita, Electron/Chromium and X11 windows, CSD and SSD, maximized, fullscreen, dialogs and popovers, and an
   external display, with screenshots.

## 7. Receipt: compositor implementation (2026-10-23, branch `claude/compositor-corners`)

What it does (`rust/pantheon-compositor`, `src/corners.rs` = numbers and policy, `src/corner_render.rs` = drawing):

- Reads `corners` from `rust/msdk/data/tokens.json` at start-up through the `msdk` crate (`CornerTokens::load`), including `style`.
- **Screen mask:** four premultiplied-black bitmaps (not a shader) in the four display corners, front-most after the pointer, so above windows, dock, panels and the lock screen; built-in output only.
- **Window clip:** each toplevel's surface elements that touch a corner box are drawn through a GLES texture shader (signed distance of a circle or of a superellipse, antialiased over one pixel). Only the pixels inside the four corner boxes of the *geometry* rectangle change, so client-drawn shadows outside the geometry, the interior and the client's size are untouched. Opaque regions exclude the corner boxes (so the corners blend), and clipped elements are never scanned out directly. `circular` is exponent 2; `continuous` is exponent 3 with the corner box 1.2x the radius (`CONTINUOUS_EXPONENT`, `CONTINUOUS_EXTENT` in `corners.rs`; eye-tuning, like the radii, is the owner's call).
- **Hug the display (geometry based, no placement state):** a toplevel corner within 1 px of a display corner uses `screen`; a corner on a screen edge but not a display corner is square; every other corner uses `window`. This covers maximized (with a top bar the top corners sit under the bar, so they are square and the bottom ones follow the display), fullscreen, tiled halves and quarters, and a floating window dragged into a corner. Radii are capped at half the shorter side.
- **Popups and menus:** `popover` on all four corners (X11 override-redirect windows are treated as popups). Dialogs are toplevels, so `window`.
- **Panels and the dock:** a corner is rounded (`window`) only if it touches no screen edge. A full-width top bar therefore stays square and a floating dock is rounded.
- **Per-output policy:** only the built-in output is rounded; every other output is square (no clipper, no mask, no cost). Built-in means the connector names the display configuration already treats as the laptop panel (`eDP-*`, plus `LVDS-*`, `DSI-*`); the nested development window (`winit`) counts as built-in so the corners can be seen without a second display.

Verified (2026-10-23):

- `cargo fmt --check`, `cargo clippy --all-targets -D warnings` (default features and `native-drm`) clean; `cargo test -p pantheon-compositor --features native-drm`: 183 + 19 passed, 28 of them new (which corner gets which radius for floating, maximized with and without the bar, fullscreen, tiled halves and quarters with and without the bar, one pixel of slack, external outputs, popups, bar and dock, tiny surfaces, token loading, the distance function, the mask bitmap and its area).
- The nested compositor starts and draws, in a private Xvfb with its own D-Bus and runtime directory (software GL, not the Asahi GPU): a plain GTK 3 window gets 12 px corners against the wallpaper; the same window maximized and fullscreen is cut at the display curve, flush with the black mask; no shader error in the log. The shader first applied to nothing on the nested output because Winit renders a vertically flipped frame (`Transform::Flipped180`); `gl_FragCoord` is now mapped for `Normal` and `Flipped180` frames. Rotated frames are drawn unclipped.

Not verified:

- **Visual acceptance on the built-in display** (curve match against the glass, light/dark, the 14 and 12 values, the continuous shape): needs the owner's eyes. Nothing was installed and nothing was loaded: the owner's running session still has the old compositor binary; the new build lives only in the shared cargo target (`debug/pantheon-compositor`) of the worktree `~/Projects/mseries-corners`.
- The **native DRM path on the Asahi GPU**: it compiles (`MultiRenderer` hands out the render device's GLES renderer and frame) but was not run there. It assumes the native frame is `Normal` (as in Smithay's DRM compositor) and that the clip shader works on the Honeykrisp driver; if the shader fails to compile the log says so and windows stay square.
- Surfaces that are **not** clipped: Snap Assist thumbnails and the workspace/overview gesture previews (scaled copies), and X11 windows are clipped only through the same Wayland surface elements XWayland provides (not separately qualified). Direct scanout of a clipped window is intentionally off while it has rounded corners. Chromium/Electron, libadwaita, CSD with shadows, dialogs and popovers on real apps are not yet qualified (work item 4); a window that straddles two outputs is clipped per output with that output's rules.
- Damage when only the radii change without a geometry change (a token edit) is not tracked; the radii are read once at start-up, so a restart applies a changed token.
