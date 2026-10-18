# Hardware support provenance

The energy recorder and power report are adapted from public MIT sources in
`omacom/omarchy-mac-pkgs` at
[`b5e10d3d5727b51fdf20c2965c9d6eaaff6842d1`](https://github.com/omacom/omarchy-mac-pkgs/tree/b5e10d3d5727b51fdf20c2965c9d6eaaff6842d1):
`omarchy-mac/lib/sleep-cost` and `omarchy-mac/bin/omarchy-power-report`.
The original copyright/permission notice is retained in `LICENSE.omacom` and
staged with these files. The branch's three source commits are `Show what
suspend costs on a Mac, and a power report`, `Add up sleeps before an unlock,
and harden the sleep hook`, and `Retry an undelivered sleep notice, and show
draw beside a weak source`; full commit IDs are in the branch survey receipt.

Bluetooth recovery and its failure/race fixtures derive from
[`aa747a8c4cbde582d06577ffab2fe3835d0eacf4`](https://github.com/omacom/omarchy-mac-pkgs/tree/aa747a8c4cbde582d06577ffab2fe3835d0eacf4),
`omarchy-mac/bin/omarchy-bluetooth-resume-fix`, `lib/bluetooth-supported`,
and `test/bluetooth-test.sh`, under the same MIT license. Original commit
authors remain linked through the immutable source history; no upstream authorship
is claimed for this port. The optional built-in-keyboard hwdb comes from
`99fac5c56e228fc664e7d9d70116dcc78c801f33`.

Elementary adaptations use logind and notify-send instead of Hyprland and
Omarchy commands. They do not import pacman hooks, repository keys or desktop
configuration. Sleep records require known charging state, matched boot IDs,
finite clock values and an observed suspended-clock interval; failed suspend
attempts cannot be labeled successful sleep measurements. Notifications remain
hidden while lock state is unknown. CPU reporting accounts for PID reuse.
Bluetooth recovery is shipped disabled pending a matching hardware failure;
F4/F5/F6 remapping is separately opt-in.

Source checks and fixture tests do not qualify hardware, a factory image or
battery improvements. See `../OMACOM-IMPROVEMENTS.md` for all dispositions.
