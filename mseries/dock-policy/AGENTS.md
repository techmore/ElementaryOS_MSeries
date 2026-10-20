# Dock incident and required approval

The user reported a floating dock that steals attention and prevents typing, and explicitly
requested that it be stopped and kept disabled. Preserve the dock-disabled marker and the
no-window launcher guard. Do not re-enable the dock or change its appearance, position,
focus behavior, launcher, or binary without explicit GUI approval of the exact prepared
change using `/home/sdolbec/.local/bin/mseries-dock-change`.

Approval must default to Cancel and expire after 90 seconds. Timeout, dismissal, missing GUI,
or GUI failure cancels without changes. Do not bypass this by invoking dock binaries directly,
removing the marker, replacing the launcher, or using an installer/revert. Automatic startup
must remain quiet. See `/home/sdolbec/.config/mseries/dock/POLICY.txt` for the complete policy.
