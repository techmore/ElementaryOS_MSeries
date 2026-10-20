# Review and validation

## Scope checks to the changed surface

Before editing, identify the relevant app, toolkit versions, nearest reusable
pattern and user-visible states. After editing, inspect the diff for unrelated
style changes and state/backend regressions. Build/test the touched component,
not the whole OS image for a documentation or small widget change.

For a consistency review, report specific findings with source locations and
user impact. Separate regressions, platform mismatches and optional polish;
existing implementations are evidence, not an automatic gold standard.

## Existing test and visual entry points

All paths below are relative to the active repository. Inspect script arguments,
fixtures and side effects before running them; use an isolated display, temporary
configuration and fake services rather than real accounts/devices.

- CodexBar: `mseries/codexbar-wingpanel/meson.build` defines model, JSON,
  presentation, helper and interaction tests. `probe/run-probe.sh` takes
  `BUILD_DIR OUT_DIR [dark|light] [scenario...]` and renders fixture states such
  as healthy, empty, busy, stale and provider-error. `probe/run-settings-probe.sh`
  renders settings pages; inspect its fixed X display before use. Reuse relevant
  existing probes for account switching and long-label popovers.
- Orchard: `mseries/orchard-incus-native/tests/test-ui.py` supplies a fake Incus
  socket and isolated config/state for the native UI smoke target. Under an
  isolated display, `meson test -C BUILD_DIR native-windows --print-errorlogs`
  exercises that target after a successful component build. It is a smoke check,
  not proof of visual consistency.
- Apple Passwords: inspect `mseries/icloud-passwords/test_gui.py` and its mocks
  before testing; keep credentials and live keychains out of fixtures.
- Troubleshooter: compare relevant light/dark retained screenshots under
  `mseries/netspeed/docs/screenshots/`, then capture changed states if needed.
- Machine Lab, Battery, Work Mode: use their current tests or isolated fixture
  launchers where available; source-only inspection does not establish a visual
  or scheduling pass. Do not activate live VMs or change wallpaper to test layout.

For changed layouts, inspect captured output in light/dark modes and a narrow
window with long text. For controls, check keyboard activation, focus order,
accessible names and pending/error recovery. Rendering probes alone do not
establish keyboard or assistive-technology behavior. Record omitted checks.

## Runtime boundaries

Follow `AGENTS.md`: routine indicator changes must preserve Wingpanel stability;
use private probes rather than restarting the owner's panel for screenshots.
CodexBar runtime changes still follow the repository's custom-port checks and
deployment requirements. A skill/documentation-only change does not deploy an
indicator or require rebuilding the desktop.

Report what was source-inspected, built, rendered, interacted with or verified
on hardware. State installed-but-not-loaded status when applicable. Do not infer
factory-image qualification or hardware success from a local build or fixture.
