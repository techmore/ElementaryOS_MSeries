# Native UI acceptance (#242)

The release gate remains open. This directory records bounded, reproducible
checks; it does not authorize `dev` → `main`, desktop reloads or device actions.

## Private responsiveness checks

```sh
bash mseries/ui-audit/run-private-checks.sh /new/private-output
```

Dependencies: Python GI, GTK 3/4 introspection, Pango Cairo, Xvfb, xauth,
D-Bus, xdotool and FFmpeg. Each toolkit runs in a separate process using private
HOME/XDG directories, private display and a bus with service activation disabled.
Only synthetic helpers/backends run. Output includes logs, PNGs and a JSON receipt
with source-file digests, theme stylesheet digests and screenshot pixel dimensions.
GTK widget scale factors are asserted at 1 and 2. Hosted Ubuntu without elementary
stylesheets uses GTK fallback and writes an explicit limitation; this does not
qualify elementary theme appearance.

- Troubleshooter: initial window remains responsive while checks load; actual
  GTK heartbeat during delayed status, confirmation and run operations; duplicate
  suppression; malformed/failed response and recovery; retained previous content;
  close cancellation and helper reaping; stale completion refusal; timeout retry.
  Model, analysis and service commands are never activated by these checks.
- AirPlay: actual GTK window with delayed fake receivers, pending state, native
  checkboxes with visible labels, failed refresh and retry, retained last-known
  receiver state, empty results, wrapped long network names in a 360px window and completion after close. No PipeWire or live audio operation.
- Displays: bounded Pango labels, system font, accessible summary and keyboard
  selection and private-window Right/Tab key delivery; fake monitor backend, never applies a display configuration.

These tests check programmatic behavior and render fixtures. They do not establish
full screen-reader traversal, key-event navigation in every dialog, live
hardware operation, or complete acceptance of the 38 surface families in the
inventory. Prior component receipts retain their original revisions and limits.
