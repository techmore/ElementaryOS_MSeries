# Rust compositor next-generation investigation — October 21, 2026

Scope: `rust/pantheon-compositor` on `origin/dev` (Smithay rev `023b78b`), plus the live
session (pid 1934, `--backend native`, J314S M1 Pro, eDP-1 3024×1964 @ 120 Hz, scale 1.25).
The owner asked for a deep look at four areas: popup attention, snapping (and adding more
apps to a snap), polling/performance/battery, and monitoring.

This is a **read-only investigation**. Nothing was edited, rebuilt or restarted. File:line
references are against `origin/dev` at `fac0e41a`. Items marked *[spec]* are inferences that
have not been reproduced. The running binary may come from the Codex deploy lineage rather
than `dev`; the compositor sources are equivalent for these findings.

## Live evidence (about 38 min of uptime, on mains, load average 11–18 from a kernel build)

| Signal | Reading |
| --- | --- |
| Compositor CPU | About 17% of one core on average (cgroup includes Xwayland). Main thread 7–12% in 10 s samples; 82% of samples sleep in `epoll_wait` |
| Flip rate | 70–116 flips/s before 17:03. About 27/s after ChatGPT (X11), Brave and a clang kernel build started |
| Pacing | `frames_queued == vblanks`, `frames_empty = 0`. Clients commit once per frame callback, so every animating client is paced at the compositor's flip rate |
| Commit attribution | "pantheon-compos(1934)" ≈ 27 commits/s is really Xwayland (ChatGPT runs with `--ozone-platform=x11`). Pid comes from the socketpair's peer credentials |
| Client rendering | Claude desktop's GPU process runs with `--use-gl=disabled` (57% CPU): linux-dmabuf is off on native, so clients render in software and upload SHM |
| Journal errors | 68 × `surface missing from known popups` (harmless Smithay noise, see §1), 219 × xwm `BadWindow` at INFO, every line PRIORITY=6 so `journalctl -p err` misses ERRORs |
| Power | SMC Total System Power 73.8 W under the build load. Battery `power_now` is battery flow, not system power |

## 1. Popups and attention

How it works: popups are tracked by Smithay's `PopupManager` (`handlers/xdg_shell.rs:44-62`),
drawn above every toplevel (`popup_stack.rs:74-139`), and grabbed in `grab()`
(`xdg_shell.rs:244-313`). Activation goes through `activation::verdict`
(`activation.rs:246-258`, `state.rs:1937-2056`). There is no window-level attention state.

| # | Severity | Defect | Fix |
| --- | --- | --- | --- |
| D1 | High | **An open popup grab silently blocks every compositor focus change.** Smithay's `PopupKeyboardGrab::set_focus` ignores focus while the grab is live, so `focus_window_keyboard`, activation, workspace switch, polkit prompts and the overview raise the target but keys still go to the old menu (`xdg_shell.rs:299-300`). `active_popup_grab` is never consulted again | `end_popup_grab_unless(root)`: `ungrab(PopupUngrabStrategy::All)` and unset keyboard and pointer grabs before any compositor-driven focus change, minimize, workspace switch, overview, and on unmap of the grab root |
| D2 | High | **X11 override-redirect windows are mapped with `activate=true`** (`xwayland.rs:173-174`). Every notification card from `notifications.py`, and every X11 tooltip or menu, deactivates the focused app. Clicking a card leaves no window with keyboard focus (`input.rs:277-285`). The `ChangeProperty` BadWindow bursts name the notification daemon's windows *[spec: likely this path racing card destruction]* | Map override-redirect windows with `activate=false`; never activate or focus override-redirect windows or `input_model() == None` windows; raise only |
| D3 | High | **No attention channel.** `Verdict::Ignore` (`state.rs:1958`) and the 8 s deferred give-up (`state.rs:2003-2008`) drop requests silently. `XwmHandler::demands_attention_request` is not implemented, `WM_HINTS` urgency is not read, and `GetWindows` has no attention field (`gala_compat.rs:21-27`) | `demands_attention: HashSet<WindowKey>` set from these paths (and suppressed new-window focus), cleared on focus; export `demands-attention` in `GetWindows` + `WindowsChanged`; dock patch shows it |
| D4 | Medium | Activation trust accepts pointer-enter/motion serials (`state.rs:1968-1980`), so hovering an app lets its later `present()` steal focus mid-typing. Under `Raise` a background app can switch workspace. X11 `_NET_ACTIVE_WINDOW` bypasses policy (`xwayland.rs:396-413`) | Trust only key/button serials from the focused client; cross-workspace or untrusted → attention instead of switching; route X11 through `verdict` |
| D5 | Medium | New windows always take focus on map (`xdg_shell.rs:468-471`, `xwayland.rs:165-168`). X11 ignores `window_type()`/transient-for and centres on the first output | Typing guard on map-focus; branch on X11 window type; place transients on their parent |
| D6 | Medium | Modals: focus goes to the parent not the modal child; dialogs centred on the work area; no `xdg-dialog-v1` or `xdg-foreign-v2`, so portal file choosers float free of Electron/Brave parents | Add `XdgDialogState` and `XdgForeignState`; redirect focus to top modal descendant; centre on parent |
| D7 | Med-low | Popup constraint box is the full output, not the work area, and `outputs_for_element().first()` picks a random monitor (`xdg_shell.rs:510-526`). Never re-constrained after parent moves | Constrain to the work area of the output under the anchor; re-run on parent move/work-area change |
| D8 | Low-med | Refused grabs (locked, root not in space) don't send `popup_done` (`xdg_shell.rs:245-260`), leaving menus that never dismiss | `send_popup_done()` on every refusal |
| D9 | Low | Focus on a dying window's popup isn't resolved to its root (`xdg_shell.rs:185-208`); `has_focus` in `publish_gala_snapshot` is false while a menu is open (`state.rs:601-607`) | Resolve through `find_popup_root_surface` |

`surface missing from known popups`: Electron/Chromium destroy `xdg_popup` but keep the
`wl_surface`; Smithay's pre-commit hook is never removed, so the next commit logs this and
returns. Harmless; not behind any user-visible bug. Silence by patching Smithay or the log filter.

## 2. Snapping, and adding more apps to a snap

Today: six zones (Left, Right, four quarters) as exact halves of the work area
(`tiling.rs:454-483`), drag zones 40 px on full output edges (`tiling.rs:486-506`),
Super+Left/Right, Super+Alt+U/I/J/K quarters, Super+Shift+Left/Right to the next monitor.
State is `tiled_windows` keyed by wl_surface (`state.rs:146,206-211`), separate from the
maximize/fullscreen maps. No Super+Up/Down, no top-edge maximize, no groups.

| # | Severity | Defect | Fix |
| --- | --- | --- | --- |
| S1 | High | No pre-snap geometry is stored. Dragging a snapped window out keeps it half-screen; no key un-snaps | Store floating rect; on drag-out restore size keeping pointer's relative title-bar point; Super+Down restores |
| S2 | High | Maximize and snap erase each other's state (`tiling.rs:272`, `pantheon_shell.rs:912-920`); un-maximize returns to an untracked tile rect | One `Placement` per window with a `prior` |
| S3 | High (multi-monitor) | `outputs_for_element().first()` iterates a HashMap built from the bbox incl. CSD shadows (`tiling.rs:162,312`, `pantheon_shell.rs:944`, `xwayland.rs:451`): snap/maximize/move-to-monitor can use the wrong monitor at random. Matches the ROADMAP's open "snap geometry discrepancy" *[spec]* | `primary_output_for(window)`: largest overlap with `element_geometry`, fallback to pointer output |
| S4 | Med-high | `apply_tile` moves the window before the client acks the resize (`tiling.rs:384-385`); `keep_clear_of_bottom_panels` on the stale commit pushes it up, leaving a recorded snap mid-screen, or drops it *[spec: Chromium/Firefox commit before ack]* | Gate placement on the configure serial via `ack_configure`/`with_committed_state`; skip keep-clear while pending |
| S5 | Med-high | Min size bigger than the zone: snap dropped, Right-side windows run off-screen (`tiling.rs:442-450`); preview promised a fit | Min-size-aware preview; on decline keep the snap anchored to the outer edge and clamp |
| S6 | Medium | Release commits the previous motion's preview rect; an auto-hide dock revealed by the bottom-edge pointer changes the work area (`move_grab.rs:68-76`) | Recompute `tile_rect` at release |
| S7 | Medium | X11 apps that resize themselves (Wine, Java, Steam) leave the zone while still marked snapped (`xwayland.rs:285-310`) | Re-send the snapped rect from `configure_request` |
| S8 | Medium | No `xdg_toplevel` `Tiled*` states, so GTK keeps rounded corners/shadows on shared edges | Set touching edges in `apply_tile` |
| S9 | Medium | Resizing a split boundary unsnaps that window; the neighbour doesn't follow | Shared-edge resize grab (design below) |
| S10 | Medium | Unplugging a monitor drops its snaps; re-plug doesn't restore (`native.rs:1425-1446`, `tiling.rs:412-414`) | Re-snap on the fallback; remember a home output by connector + EDID |
| S11–S17 | Low | Shared-edge zones snap mid-crossing; `1.min(width)` should be `width.max(1)` (`tiling.rs:473-474`); X11 snap before wl_surface exists no-ops; Super+Shift on a maximized window keeps old size; preview is a flat square overlay drawn above the dragged window (`cursor.rs:135-145`); `map_element` still raises in resize grab and overview exit; restored minimized snapped windows use stale rects | See the respective sites |

### Design: Snap Assist and snap groups

Behaviour (macOS/Windows-class, expressed in elementary style):

1. **Snap Assist.** After a snap leaves empty zones, show live scaled thumbnails of the
   other windows on that output and workspace in the empty zone. Arrows/Tab, Return/click
   to place, Escape to dismiss. Reuses the gesture `PreviewWindow` live rendering
   (`cursor.rs:465-481`), so clients are not resized.
2. **Insert by drag.** Dragging over a group member shows "replace" (centre) and "split"
   (half nearest the pointer). Splitting turns halves into 1+2, then quarters. This is how
   a third and fourth app join.
3. **Layouts.** Halves, thirds, ⅔+⅓, 1+2, 2×2, from a top-edge layout strip, a key, or the
   title-bar menu (`xdg_toplevel.show_window_menu` is not implemented yet).
4. **Groups** raise, minimize, restore and move together; shared edges resize together;
   closing a member lets its sibling grow; one remaining window stays tiled.
5. **Keyboard.** Super+Left/Right snap and start Assist, repeat cycles ½ → ⅔ → ⅓, opposite
   direction restores; Super+Up maximize, Super+Down restore; Super+Shift+Ctrl moves a group.

Data model (a split tree; halves, quarters, 1+2 and thirds are just shapes):

```rust
pub type WindowKey = usize;            // smithay Window::id(), already the Gala uid
pub enum SnapNode {
    Leaf(Option<WindowKey>),           // None = empty zone offered by Assist
    Split { axis: Axis, ratio: f32, a: Box<SnapNode>, b: Box<SnapNode> },
}
pub struct SnapGroup { id: SnapGroupId, output: OutputKey, home_output: OutputKey,
                       workspace: usize, root: SnapNode, gap: i32 }
pub enum Placement {
    Floating,
    Tiled { group: SnapGroupId, zone: ZonePath },
    Maximized { prior: Box<Placement> },
    Fullscreen { prior: Box<Placement> },
}
pub struct WindowRecord { placement: Placement, floating: Rectangle<i32, Logical>,
                          pending: Option<PendingConfigure> }   // ack-gated move (S4)
pub struct Tiling { windows: HashMap<WindowKey, WindowRecord>,  // replaces three maps
                    groups: HashMap<SnapGroupId, SnapGroup>, assist: Option<SnapAssist> }
// pure + unit-testable; clamps ratios to members' min sizes
fn layout(node: &SnapNode, area: Rectangle<i32, Logical>, mins: &dyn Fn(WindowKey) -> Size<i32, Logical>)
    -> Vec<(ZonePath, Option<WindowKey>, Rectangle<i32, Logical>)>;
```

Dock/taskbar: add optional `snap-group`, `snap-zone`, `snap-output` keys to `GetWindows`
(a dictionary, so upstream-compatible), plus `org.techmore.mseries.Snapping`
(`GetGroups`, `FocusGroup`, `MinimizeGroup`, `TileWindow`, `StartSnapAssist`,
`GroupsChanged`). The Work Mode taskbar shows "Snapped with …" and a restore-group action.

Smithay provides stacking, configure serials/ack, `Tiled*` states,
`X11Surface::configure_with_sync`, grabs and render elements. To build: the tree and solver,
Assist/picker UI (the compositor has no text rendering yet), group rules, output identity
across hotplug, D-Bus API, dock patch, spring animations (reuse `gesture_animation.rs`).

Phases: **0** correctness S1–S8 + S12, Super+Up/Down, unit tests (only one tiling test
exists, `tiling.rs:512`). **1** Snap Assist for halves → two-member group with shared-edge
resize. **2** split-on-drop, templates, picker, hotplug survival. **3** group minimize and
moves, D-Bus `Snapping`, taskbar UI, gaps and `edge-tiling`.

## 3. Performance and battery

The compositor is not CPU-bound and already uses damage tracking (`OutputDamageTracker`,
buffer age, `FB_DAMAGE_CLIPS`) and event-driven wakeups. The cost is around it.

| Rank | Win | Evidence | Risk |
| --- | --- | --- | --- |
| P1 | **Enable linux-dmabuf on native by default**, with a scanout tranche (`DmabufFeedbackBuilder::add_preference_tranche(.., TrancheFlags::Scanout, ..)`) | Opt-in only (`native.rs:2078`), not set in the unit. Electron/Chromium fall back to software GL (Claude GPU process 57% CPU) and the compositor uploads every SHM frame on its main thread. Xwayland likely can't use glamor *[spec]* | Medium: README's documented failure is a blank window on import failure. Trial login with `PANTHEON_ENABLE_DMABUF=1` first |
| P2 | **Target frame callbacks** | `native.rs:1905-1916` sends callbacks to every window on every flip with `Duration::ZERO` and claims every output, so occluded windows animate at full rate (doubled with two monitors). Empty frames send no callbacks (`native.rs:795`) | Low. Use `update_surface_primary_scanout_output` + `send_frame(.., Some(1 s), surface_primary_scanout_output)`; send callbacks (or arm an estimated-vblank timer) on empty frames |
| P3 | **Idle and DPMS** | No ext-idle-notify, idle-inhibit, `org.gnome.Mutter.IdleMonitor` or DisplayConfig `PowerSaveMode`: the panel never blanks on its own | Medium (DCP power-cycle reliability). `IdleNotifierState`, `IdleInhibitManagerState`, IdleMonitor D-Bus, `DrmCompositor::clear()` for off |
| P4 | **Frame-timing instrumentation** | Explains the 27 fps drop: GPU contention (Asahi rejects HIGH-priority queues without `CAP_SYS_NICE`, `drivers/gpu/drm/asahi/file.rs:921` *[spec: running kernel matches]*), starved kernel workers at load 14–18, or SHM uploads | Low. See §4 |
| P5 | 60 Hz on battery (optional) | Clients are paced by the compositor, so 60 Hz halves continuous-animation work | Low-med |
| P6 | Direct scanout / overlays after P1 | Windows render as `Kind::Unspecified` (`popup_stack.rs:114,128`), so overlay planes are never used | DCP plane limits |
| P7 | Small CPU items | Wallpaper lacks an opaque region and is resampled each repaint (`wallpaper.rs:88-95`); `SolidColorBuffer::new` per frame re-damages overlays (`cursor.rs:138,250`); `update_fractional_scale_preferences` per render (`native.rs:772`); per-commit `SO_PEERCRED` syscall + global mutex (`handlers/compositor.rs:41`); ~130 redraw requests/s not coalesced (use a calloop `Ping`); `publish_gala_snapshot` rebuilds all windows after every dispatch (`main.rs:111`, `state.rs:559-621`); 8 ms gesture settle timer (`gesture_animation.rs:234`) | Low |
| P8 | Release profile | No `[profile.release]`: opt-level 3, no LTO, 16 codegen units, no `target-cpu`. Add `lto = "thin"`, `codegen-units = 1`, `-C target-cpu=apple-m1` | Low; *[spec]* 5–15% |

Not a problem: apple-drm has no cursor plane (`apple_drv.c:571-573`), so pointer motion
always composites, but damage keeps it to the cursor area. Logging at ~21 lines/min is cheap.

Latent bug: `render()` never checks `RenderFrameResult::needs_sync()` before `queue_frame`
(`native.rs:787-806`). Harmless on apple-drm (`IN_FENCE_FD`), wrong on drivers without fences.

## 4. Monitoring

Exists: 30 s `redraw stats` (`redraw_stats.rs`, timer `state.rs:334-342`), opt-in display
trace (`display_trace.rs`, enabled by the user drop-in `display-trace.conf`), `READY=1` only,
session scripts `collect-session-metrics.sh` / `summarize-metrics.py` / `dashboard.html`,
`mseries/power/audit/*`, battery logger with energy-by-app from CPU share. Four separate
copies locate the SMC power sensor; `sample_power.sh` hardcodes `hwmon2`.

Gaps: no frame timing (vblank `EventMetadata` timestamp and sequence are discarded at
`native.rs:1891`), no per-output stats, wrong Xwayland attribution (`X11Surface::pid()`
exists), no shm/dmabuf or damage share, no energy correlation, no watchdog (`WatchdogUSec=0`),
journal ANSI codes + duplicate timestamps + every line PRIORITY=6.

Design:

- `src/metrics/{mod,histogram,output,client}.rs`. Fixed 84-bucket log histogram
  (1 µs–2 s), `OutputStats` per output (render CPU, queue→flip, dirty→flip p50/p95/p99,
  late frames, empty ratio, zero-copy share, damage %), `ClientStats` in `ClientState`
  with pid cached at connect (commits, shm vs dmabuf, damaged px, frame callbacks).
  Overhead: ~3 `Instant::now()` per frame, a few relaxed atomics per commit, net cheaper
  than today's per-commit syscall.
- D-Bus `org.techmore.mseries.Compositor.Stats` (`GetSnapshot`, `GetClients`) on the
  existing gala-compat connection, computed only on request; CLI
  `src/bin/pantheon-compositor-stats.rs` (`top`, `--json`, `--power`).
- `sd_notify` `WATCHDOG=1` + `STATUS=` (fps, commits/s, top client) every `WatchdogSec/3`.
  `WatchdogSec=30s` needs owner approval: a restart kills every Wayland client.
- `tracing-journald` (or `.with_ansi(false).without_time()` under systemd), default
  filter `info,smithay::xwayland::xwm=warn`, unchanged reconcile results at DEBUG.
- Benchmark: shared `mseries/power/sensors.py` (find Total System Power by label) and
  `mseries/benchmarks/power_scenarios.py` via `run.py --suite power` (idle 5 min, mpv
  1080p, self-scrolling page; quiet-system precheck; ABAB × 3 as `POWER-ROADMAP.md` requires).
- Energy hogs: the battery logger (already waking every 15 s) calls `GetClients`; the
  Battery app gets a "screen updates" column; the high-drain alert names the redrawing app
  (roadmap G4). No new indicator.

## Progress (2026-10-21)

Landed in `dev`: snapping phase 0 (#449) and Snap Assist with two-member groups (#453); frame metrics, targeted frame
callbacks and P7/P8 (#452); dmabuf on by default and the systemd watchdog (#456); power scenario harness (#448); idle
monitor, idle inhibit and screen blanking (P3, this branch). Popup/attention D1/D2/D3/D8 is PR #450. All of it is
unqualified on hardware until the next login; checklists are in `mseries/OS9-HANDOFF.md`.

## Recommended order

1. **Measure first:** metrics phase 0–1 (journal fixes, correct attribution, frame timing).
   Cheap, and it turns every later change into a before/after number.
2. **Popup/attention D1 + D2 + D8**: small, high-impact focus fixes.
3. **Battery P2 + P7**, then the **P1 dmabuf** trial login, then **P3 idle/DPMS**.
4. **Snapping phase 0** (S1–S8), then **Snap Assist for halves** (phase 1).
5. **Attention channel D3** with the dock patch, then D4–D6.
6. Snap groups phases 2–3, D-Bus `Snapping`, taskbar UI; overlays (P6).

Each compositor change loads at the next login; routine deploys must not restart the
running compositor, Wingpanel or dock.
