# Bounded native dock trial

The controller requires the fixed compositor's `FocusRoutingVersion` and a live
executable hash matching `/usr/bin/pantheon-compositor`. It never enables a dock
against the older running session. The GUI waits for an explicit Start click.

Two independent systemd mechanisms enforce the duration, even if GTK loses
focus or crashes: `RuntimeMaxSec` with `Restart=no` on the dock service, and a
separate user timer that restores the owner's exact disabled marker and stops
the entire dock service control group. Stop/close/focus loss also ends the trial.
The service's stop hook restores the marker on early exit, crash or timeout.

The test checks native half-width snapping, then real text delivery into its own
entry while the dock runs. Its focus monitor cancels on any focus departure;
this is a precaution, not proof that every departure was caused by the dock.
No typed user text is saved. Results record geometry, booleans and stop reason.

Install the script privately and create the safety units without starting a dock:

```sh
install -Dm755 mseries/dock-trial/dock-trial.py ~/.local/libexec/mseries-dock-trial
~/.local/libexec/mseries-dock-trial --configure --seconds 60
```

Run the GUI after loading the updated compositor:

```sh
~/.local/libexec/mseries-dock-trial --seconds 60
```

`--stop` restores the disabled state and stops the dock. `--restore` only restores
the marker and is used by ExecStopPost. A later explicitly requested trial can
use `--seconds 120`, up to 600. Permanent enabling requires a separate owner
request; no trial enables it permanently. The cap and disabled state remain.

`--after-login` runs only while a private pending-login-trial marker exists. It
waits up to 40 seconds for the fixed compositor, consumes that marker and removes
its own one-time autostart entry before showing the GUI. The October 20 live
setup writes the report to this chat's outputs using `--report`; the default is
`~/.local/state/mseries/dock-trial/latest.json`.

Verification: `python3 mseries/dock-trial/test-controller.py` covers old-compositor
refusal, failed-watchdog refusal, exact opt-out restoration, and stop behavior
during marker I/O or timer-stop failure. A live five-second watchdog exercise,
with the real dock left disabled throughout, fired the stop service successfully
on October 20. Runtime policy was then restored to 60 seconds. The post-login
native trial is pending; this setup is not its result.
