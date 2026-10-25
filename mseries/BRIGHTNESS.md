# Display brightness: investigation, design and roadmap

Owner request (2026-10-14): the lowest brightness is not low enough; it should be
"virtually off". This file is the single reference for the finding, the design that
answers it, what is and is not verified, and the plan to finish. Day-to-day progress
is logged in `OS9-HANDOFF.md`; the bug rows are in `BUG-FIX-ROADMAP.md`.

Status 2026-10-16: **implemented in the repo; the helper is installed and running on the
M1 Pro; the patched Gala and Quick Settings plugin are installed but not yet loaded
(they need a fresh login). Nothing has been looked at on the panel at the new low
levels.** No claim below about how the dim end *looks* is made until the owner has
checked it.

## 1. Goals, non-goals, acceptance

Goals

1. The dimmest setting is dark enough for a dark room at night ("virtually off") on the
   built-in panel, without ever turning the panel fully off by accident.
2. Each brightness-key press is an even, noticeable step, including at the dim end.
3. One brightness scale shared by the keys, the Quick Settings slider and the OSD.
4. Nothing regresses: manual brightness stays put (no ambient or idle dimming), suspend
   and lid handling, screenshots, external monitors, the login screen.
5. Everything is reversible, recorded, and reproducible from the repository.

Non-goals

- Ambient auto-brightness (deliberately off since 2026-10-14, see the dimming fix).
- Kernel or DCP firmware changes: the kernel feature set is DeepSeek's. Questions for
  them are listed in section 8.
- HDR, True Tone and colour management (separate rows in `ROADMAP.md`).

Acceptance (all must hold before the P2 bug row is closed)

| ID | Criterion | How measured |
|---|---|---|
| A1 | Lowest key step reads as "virtually off" to the owner in a dark room | Owner look, recorded in the handoff; luminance number if a meter is available |
| A2 | Every step from lowest to highest is within 1.5x of its neighbour, except integer-limited 2→3 | `test_keys.py` (passes) |
| A3 | Keys and slider agree: moving one moves the other, and the OSD matches | Manual check, section 6 |
| A4 | A screenshot taken at any dim step has normal colours | Manual check, section 6 |
| A5 | Brightness and dim state survive suspend/resume and lid close/open | Manual check, section 6 |
| A6 | If the patched Gala is absent or crashes, the keys still work and stop at 2 nits | Manual check, section 6 |
| A7 | No visible banding at the deepest step on a dark gradient, or a documented decision to accept it | Owner look |

## 2. Findings

### 2.1 The panel and its driver

- Device: `/sys/class/backlight/apple-panel-bl`, `type=platform`, `scale=linear`,
  `max_brightness=500` (from the device tree: `apple,max-brightness = 0x1f4`). The unit is
  **nits**, not a percentage of an abstract range.
- Driver: `drivers/gpu/drm/apple/dcp_backlight.c` (Asahi tree; the OpenBSD copy has the
  same constants). `calculate_dac()` maps 2–99 nits and 103–510 nits through two lookup
  tables. **Any value at or below `MIN_BRIGHTNESS_PART1` (2) selects the same DAC value**,
  so 0, 1 and 2 are identical. The hardware floor is therefore **2 nits**.
- `bl_power`, `actual_brightness` (reads about 1 above `brightness`, e.g. 31 for 30) and
  `brightness` are the files that matter; `brightness` is writable by root only, so user
  code writes through logind.
- The DCP firmware logs `handle_stage1_enable blm_en 1 ltm_en 0` at start: the mini-LED
  backlight manager is on. Known upstream oddities that matter for testing low values:
  AsahiLinux/linux#499 (brightness can be stuck in two states until a suspend/wake cycle),
  and `nitsToDBV: iDAC out of range` messages that upstream found are not an error
  indicator. Neither was seen on this Mac this boot.

### 2.2 Why the floor was 5 nits

- Mutter's sysfs backlight computes `min = MAX(1, max/100)` (`meta-backlight-sysfs.c`),
  which is **5 of 500**. Its `Backlight` property clamps the reported value to that, and
  `SetBacklight` clamps writes to it.
- Every control here went through Mutter: the key helper, the Quick Settings slider and
  `shell-bridge.py`. So the controls stopped 2.5x above what the hardware can do.
- A key press moved 5% of 500 = **25 nits**, so from a dim 30 nits one press landed on the
  floor and the dim end had effectively two usable levels.

### 2.3 Dead ends (read-only probes, 2026-10-16)

| Idea | Result |
|---|---|
| Dim with the display's gamma lookup table (what night light does) | `GetCrtcGamma` returns empty arrays; `NightLightSupported=false`; `supports-color-transform=false`. The DCP CRTC exposes no LUT here. |
| Separate always-on-top overlay program | The compositor exposes no `wlr-layer-shell` (globals seen: gtk_shell1, wp_viewporter, wp_presentation, wp_color_manager_v1, io_elementary_pantheon_shell_v1). |
| `brightnessctl` / Omarchy approach | Same 1% = 5 nit floor; see 2.4. |
| Write `bl_power`, brightness 0 | Not a dimming tool: 0 is the same DAC as 2 and `bl_power` switches the panel off. Used only by docked-lid on purpose. |
| Colord ICC `vcgt` profile swaps | Needs a gamma LUT, which does not exist; also flickers on change. |

### 2.4 Prior art surveyed

- `omacom/omarchy`, `omacom/omarchy-mac` (`quattro`, 242 branches), `omacom/omarchy-mac-pkgs`,
  `maralcbr/omarchy-mx-mac` (82 branches): all use `brightnessctl -d apple-panel-bl set N%`
  with a 1% minimum and 1% steps at or below 5%. Their only display fixes are choosing
  `apple-panel-bl` over the Touch Bar's DSI backlight (#170), propagating
  `brightnessctl` failures (#429) and skipping the DDC probe (#472). No branch, issue, PR
  or commit in any of them mentions a minimum-brightness problem or sub-floor dimming.
- `maralcbr/linux` (kernel fork, 26 branches) has no change to `dcp_backlight.c`.
- AsahiLinux/linux: no open issue or PR about a lower minimum. Related: #499, #489
  (auto-brightness distracting), #223 (`actual_brightness` wrong).
- Conclusion: nobody has solved this; the approach below is original work, and
  upstreamable pieces are listed in section 8.

### 2.5 Everything that reads or writes the backlight

| Component | File | Path used | Floor | Changed? |
|---|---|---|---|---|
| Brightness keys | `mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness` | sysfs read, logind write, Mutter fallback; Gala dim file | 2 nits (+4 software steps with patched Gala) | **Yes** |
| Quick Settings slider | `mseries/quick-settings/ScreenBrightness.vala` | sysfs read, logind write, Mutter fallback | 2 nits; clears the dim layer | **Yes** |
| Software dim layer | `mseries/patches/gala-screen-dim.patch` | Gala actor, state file | n/a | **New** |
| Idle dim / auto brightness bridge | `mseries/brightness/shell-bridge.py` | Mutter `SetBacklight` | 5 nits | No (both features are off; see roadmap BR-10) |
| Docked lid | `mseries/docked-lid/mseries-docked-lid` | logind write 0, restore | n/a | No (see BR-09 for the dim file) |
| Lid trace | `mseries/lid-trace/mseries-lid-trace` | read only | n/a | No |
| Keyboard backlight | `mseries/keyboard-backlight/backlight.py`, `KeyboardBrightness.vala` | separate LED (`kbd_backlight`, 0–255) | n/a | No |

## 3. Design

### 3.1 One perceptual scale

`nits = 2 + (max - 2) * level^2.2` for `level` in 0..1 (gamma 2.2 is the usual perceptual
exponent for display luminance). `--set N` and the slider use `level`; `--nits` is exact.

The keys do **not** step the level evenly. They walk a *ladder* of distinct integer nit
values: the curve sampled every 5% of level (21 points), then integer geometric midpoints
inserted wherever neighbours differ by more than 1.45x. Result (500-nit panel):

`2, 3, 4, 5, 7, 10, 13, 16, 20, 26, 37, 51, 68, 88, 110, 136, 164, 195, 229, 266, 307, 350, 397, 447, 500`

Keys move to the next ladder value above or below the *current* brightness, so they keep
working after the slider or anything else changed it. Keys never go to 0.

### 3.2 Software steps below the floor

When the patched Gala is running, four more steps follow, brightest first, at
0.7, 0.5, 0.35 and 0.25 of the 2-nit luminance (1.4, 1.0, 0.7, 0.5 "virtual nits"). The
backlight stays at 2 nits and a black layer is blended over the panel. Blending happens in
encoded colour, so the alpha is corrected for display gamma:
`alpha = 1 - (virtual / 2) ^ (1 / 2.2)`, capped at 0.85 so a bad value can never black the
screen out.

| Virtual nits | Alpha |
|---|---|
| 1.4 | 0.150 |
| 1.0 | 0.270 |
| 0.7 | 0.379 |
| 0.5 | 0.467 |

These factors are a first guess. They are tuned in BR-02 once the owner has looked.

### 3.3 Data flow

```
 brightness key ─▶ Gala accelerator ─▶ mseries-brightness ─▶ logind SetBrightness ─▶ apple-panel-bl (2…500 nits)
                                            │
                                            └─ below 2 nits ─▶ $XDG_RUNTIME_DIR/mseries-dim (alpha, atomic rename)
                                                                      │ inotify
 Quick Settings slider ─▶ logind SetBrightness, then clears the file ─┤
                                                                      ▼
                          patched Gala: ScreenDim actor (black, click-through, hidden during screenshots)
                          writes $XDG_RUNTIME_DIR/mseries-dim.gala (its PID) so writers know it is alive
```

- `dim_supported()` is true only if that PID file names a live process called `gala`. A
  stale file, stock Gala or a crashed compositor all read as "unsupported", and the keys
  fall back to the 2-nit floor.
- The state file lives in the runtime directory, so it vanishes at logout and the next
  session starts un-dimmed. The backlight value itself persists in the kernel.

### 3.4 Failure behaviour (designed, to be verified)

| Failure | Behaviour |
|---|---|
| logind refuses `SetBrightness` | Falls back to Mutter `SetBacklight` (5-nit floor), logs to stderr |
| Gala dies while dimmed | Layer disappears with it; backlight is at 2 nits; keys work |
| Patched Gala fails to start | Launcher starts stock Gala and writes `~/.cache/mseries-gala-failed` |
| Dim file corrupt, NaN, negative, over 1 | Read as no dim; Gala caps at 0.85 |
| Slider used while dimmed | Writes the backlight, then writes `0` to the dim file |
| External monitor | Layer only covers `is_builtin()` monitors |

## 4. Implementation inventory

| Piece | Where |
|---|---|
| Key helper (curve, ladder, logind write, dim file) | `mkosi.images/apple-silicon/mkosi.extra/usr/libexec/mseries-brightness` |
| Tests (20) | `mseries/brightness/test_keys.py`, `mseries/brightness/test_bridge.py` |
| Slider | `mseries/quick-settings/ScreenBrightness.vala` (patch set: `mseries/patches/quick-settings-brightness.patch`, installer `mseries/install-quick-settings-brightness.sh`) |
| Dim layer | `mseries/patches/gala-screen-dim.patch` (on top of `gala-screen-corners.patch`, Gala `f0791434`) |
| Gala installer | `mseries/install-gala-screen-corners.sh` (private prefix `/usr/local/lib/mseries/gala`, per-user drop-in, stock fallback launcher) |
| Docs | `mseries/DESKTOP-SETUP.md`, this file, `OS9-HANDOFF.md` |

Helper usage: `mseries-brightness` (key daemon), `--status` (read-only, also reports dim
state), `--set 1-100` (perceptual level, one-time), `--nits N` (exact, below 2 uses the dim
layer), `--help`.

## 5. Verification status (2026-10-16)

| Item | State |
|---|---|
| Curve, ladder, dim math, dim-file handling, support detection | Unit-tested (20 tests pass) |
| Helper syntax and `--status` on the M1 Pro | Checked (read-only) |
| Key ladder in real use | Observed indirectly: the owner's brightness moved 105 → 88 → 68 after install |
| Slider widget | Typechecked with `valac`; plugin built and installed; **not loaded or used yet** |
| Gala dim patch | Both patches apply in order to a fresh checkout; full Gala built and installed; **not running yet** (needs login); screenshot hiding and PID file untested |
| Sub-2-nit look, banding, recording capture | **Unverified** |
| Suspend/resume, lid, docked lid with the dim layer | **Unverified** |
| Mutter's reaction to a backlight below its 5-nit minimum | **Unverified** (needs a write at 2–4 nits; Mutter should only clamp the value it reports) |
| `test-image-wiring.py` | One pre-existing failure in the `mkosi.finalize` test, identical without these changes |

## 6. Owner test protocol (after logging out and in)

Dark room, panel at a normal level first. Do not use ambient auto-brightness.

1. `~/.local/libexec/mseries-brightness --status`: expect `software dim: running`.
2. Tap brightness-down repeatedly. Note the step where it first feels "low enough", and
   whether any step looks like a jump. Continue to the last step (0.5 virtual nits).
3. Look at a dark gradient (a dark wallpaper or terminal) at the last step: note banding.
4. Open the gear menu: the slider should sit at its lowest when at 2 nits or below. Drag
   it up: the dim must clear. Drag it down and press the key: they must agree.
5. Take a screenshot at a dim step (area and full): colours must look normal.
6. Record the screen for 3 seconds at a dim step and check whether the layer is in the video.
7. Suspend and resume, then close and open the lid: brightness and dim must be as before.
8. Plug in an external monitor: it must not be dimmed.
9. Log out: the greeter is stock Gala at 2 nits; log in: session starts un-dimmed.
10. Kill the dim layer path (`bash mseries/install-gala-screen-corners.sh --disable`, log in): keys must stop at 2 nits and nothing else breaks.

Record each result in `OS9-HANDOFF.md`. If a meter or phone lux app is available, record
lux at the lowest step 5 cm from the panel for A1.

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Patched Gala breaks the session | Low (per-user, stock fallback, 15 s guard) | High | `--disable`, delete the drop-in, or `~/.cache/mseries-gala-failed` |
| Gala package update changes the patched files | Medium | Medium | Patches pin SHA `f0791434`; installer refuses other Gala versions; revisit per release (BR-14) |
| Banding at deep steps (8-bit alpha blend) | Medium | Low–Medium | BR-04: shader with dithering; cap alpha |
| Screen recording captures the dim layer | Medium | Low | BR-05: hide during screencast frames |
| Low backlight values trigger the Asahi stuck-state bug (#499) | Low | Medium | Test; suspend/wake clears it; report upstream with evidence |
| Overlay costs power or frame time | Low | Low | BR-06: measure with `mseries/benchmarks/` |
| Two writers disagree (bridge vs keys) | Low (bridge features off) | Low | BR-10 |
| Screen dim mistaken for a dead display | Low | Medium | Cap alpha; lowest step still readable; document the keys |

## 8. Roadmap

Legend: **Now** = next session; **Next** = after owner validation; **Later** = hardening
and polish. Owners are roles: *owner* = the Mac's owner; *impl* = Codex/Claude; *DeepSeek*
= kernel work; *build* = OpenCode build analysis.

### Phase 0: done (2026-10-16)

| ID | Item | Result |
|---|---|---|
| BR-00a | Root-cause the 5-nit floor | Mutter `MAX(1, max/100)`; hardware floor 2 nits |
| BR-00b | Survey Omarchy and Asahi prior art | No existing sub-floor work |
| BR-00c | Perceptual curve, even ladder, logind write path | Implemented, tested, installed (helper) |
| BR-00d | Software dim layer in Gala, installer, slider clearing | Implemented, built and installed; not yet running |
| BR-00e | Probes: no gamma LUT, no layer-shell | Documented in 2.3 |

### Phase 1: validate with the owner (Now)

| ID | Item | Acceptance | Owner |
|---|---|---|---|
| BR-01 | Log in to the patched Gala and run the section 6 protocol | A1, A3–A6 recorded in the handoff | owner, then impl to read the results |
| BR-02 | Tune the four sub-floor factors and the cap from the owner's look | Owner confirms the lowest step is "virtually off"; constants updated in the helper, tests and this file | impl |
| BR-03 | Confirm `--status` reports the dim layer; read the journal for Gala start-up warnings; confirm no `mseries-gala-failed` flag | Journal clean of `ScreenDim` warnings | impl |

### Phase 2: quality and robustness (Next)

| ID | Item | Acceptance | Owner |
|---|---|---|---|
| BR-04 | Replace the alpha blend with a Cogl/Clutter effect that multiplies in linear light with ordered dither, if A7 fails | No visible banding on a dark gradient at the lowest step | impl |
| BR-05 | Keep the dim layer out of screen recordings (PipeWire/portal) | Recording at a dim step has normal colours | impl |
| BR-06 | Measure power and frame cost of the layer (idle and scrolling) with `mseries/benchmarks/` | No measurable regression (median of 5, A/B), recorded honestly | impl |
| BR-07 | Smooth transition: ease the backlight/layer over about 120 ms between steps so there is no flash when crossing 2 nits | No visible flash going up or down through the floor | impl |
| BR-08 | Sub-floor slider range: let the slider's bottom segment cover the four software steps, with one shared scale | A3 for the full range, tests for the mapping | impl |
| BR-09 | Teach `mseries-docked-lid` to clear and restore the dim file around a lid cycle | Docked lid open restores both backlight and dim; covered by a unit test | impl |
| BR-10 | Make `shell-bridge.py` (idle dim / auto brightness) respect the 2-nit floor and the dim layer, or retire it | Either path documented; tests updated; features stay off by default | impl |
| BR-11 | OSD level for sub-floor steps (today they show as empty) | OSD shows four distinct low positions | impl |
| BR-12 | Survive a Gala restart while dimmed (state file is re-read on start; confirm) | Restart Gala from a TTY and see the dim return | impl |

### Phase 3: packaging and release

| ID | Item | Acceptance | Owner |
|---|---|---|---|
| BR-13 | Ship helper, slider patch and Gala dim patch in the factory image overlay and first-boot module; add them to `test-image-wiring.py` | Image tests assert the files; CI green | impl, build |
| BR-14 | Gala/Quick Settings version guard in CI: fail loudly if the pinned SHA or patch no longer applies | `validate-mseries.yml` applies both Gala patches to the pinned SHA | build |
| BR-15 | Add the brightness suite and a `valac` typecheck of the slider to `validate-mseries.yml` (the suite is already discovered there) | CI runs `test_keys.py`; typecheck step added | build |
| BR-16 | Fix the pre-existing `test-image-wiring.py` finalize failure | Test passes on a clean tree | impl |

### Phase 4: upstream and platform (Later)

| ID | Item | Notes | Owner |
|---|---|---|---|
| BR-17 | Ask DeepSeek whether the DCP firmware accepts a lower luminance than 2 nits (the driver clamps; macOS's behaviour is not measured here) and whether `iDAC out of range` can be avoided | A GitHub question, no kernel change by us; a hardware floor beats a software one | DeepSeek |
| BR-18 | Report to GNOME: Mutter's `min = max/100` rule is wrong for nit-calibrated panels (suggest a driver-provided minimum) | Issue with this analysis | impl |
| BR-19 | Offer elementary the perceptual curve for the Quick Settings brightness slider | Upstream PR once BR-08 lands | impl |
| BR-20 | Offer `omacom/omarchy-mac` the ladder and the finding (their 1% = 5 nit floor) | Issue, not a code import; respect their licence and attribution rules | impl |
| BR-21 | Evaluate a proper DRM atomic property or Mutter feature for dimming on DCP panels | Only if the kernel ever exposes a LUT or CTM | DeepSeek |

### Sequencing

1. BR-01 → BR-03 (the owner's login).
2. BR-02 immediately after, because everything else tunes around the final steps.
3. BR-04/05/07/11 only if the owner's look shows the issue; otherwise defer.
4. BR-08/09/10/12 are robustness and can run in parallel in separate files
   (helper, Vala, docked-lid) with one writer per file.
5. BR-13 → BR-16 once the behaviour is accepted; release gate is a full section 6 pass.

### Definition of done for the P2 bug row

A1–A7 all pass or have a recorded, owner-approved exception; BR-01, BR-02, BR-09 and
BR-13 are complete; the handoff has the measured result; this file's status block is
updated.

## 9. Rollback

| Layer | Undo |
|---|---|
| Key helper | `cp ~/.local/libexec/mseries-brightness.bak-20261016 ~/.local/libexec/mseries-brightness`, restart it |
| Quick Settings plugin | `bash mseries/install-quick-settings-brightness.sh --uninstall`, reload Wingpanel |
| Patched Gala | `bash mseries/install-gala-screen-corners.sh --disable`, log in again (the private build stays in `/usr/local/lib/mseries/gala`) |
| Dim state | `rm $XDG_RUNTIME_DIR/mseries-dim` |
| Build packages installed 2026-10-16 | `libgnome-bg-4-dev libadwaita-1-dev libpackagekit-glib2-dev libaccountsservice-dev libportal-dev` (apt; harmless to keep) |
