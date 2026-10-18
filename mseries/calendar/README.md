# Pantheon calendar agenda

The datetime indicator has **Events** and **Tasks** tabs above the calendar's
right pane. Events follow the selected day. Tasks shows all incomplete tasks
from selected, enabled elementary Tasks lists, including tasks with no due
date. Dated tasks sort first, then undated tasks alphabetically. Activate a
task to open elementary Tasks; completion and editing stay in that app.

Both tabs use Evolution Data Server (EDS), the native Calendar/Tasks store.
Updates, deletions, source selection and account additions are observed live.
Identical UIDs in separate calendars do not hide each other's events.

## Google Calendar

Choose **Calendar Accounts…**, add **Google**, complete the browser sign-in and
consent, and enable **Calendar**. The launcher opens GNOME Online Accounts via
GNOME Settings (with a process-local desktop override), or the standalone GTK
account frontend if Settings is unavailable. EDS discovers Google calendars
from that account and supplies them to Events. The account frontend, EDS and
Tasks are included in the Apple Silicon image dependency list.

Google authorization must be completed by the account owner. The repository
contains no Google credentials or tokens. OAuth and refresh credentials stay
with the desktop account service and keyring. Network changes synchronize on
EDS's backend schedule; this panel does not add a separate polling loop. The
panel is an agenda; event edits in a native EDS calendar client synchronize
through the same backend. Gmail mail access is not required for calendar use.

Google Calendar and Google Tasks are different services. The Tasks tab reads
whatever task lists elementary Tasks has configured; enabling Google Calendar
does not imply that a Google Tasks list is available.

## Build and install

Upstream: [elementary/panel-datetime](https://github.com/elementary/panel-datetime),
revision `d0b3a703a7efbb5b3040d7be1ccb616eeb919c54`, GPL-3.0-or-later
(repository COPYING; individual files retain their existing notices).
Our changes are `../patches/datetime-agenda-tabs.patch`; the source pin and
artifact path live in `../panel-factory-pins.json`.

Prerequisites: `git meson ninja-build valac pkg-config libwingpanel-9-dev
libgranite-7-dev libgtk-4-dev libadwaita-1-dev libecal2.0-dev
libedataserver1.2-dev libical-dev` plus the installed datetime 2.4.2 package.

Run `bash mseries/install-calendar-agenda.sh`; reload Wingpanel to activate.
The installer saves the package-versioned original and replaces the library by
rename. `bash mseries/install-calendar-agenda.sh --uninstall` restores the
original indicator and removes the installed account launcher. Accounts and
personal task/calendar data are preserved.

Factory builds use the same pin and patch in `build-desktop-indicators`; the
account launcher is staged into immutable `/usr/bin`. A source build does not
qualify a factory image or a Google account connection.

## Validation

`bash mseries/calendar/test-agenda.sh /absolute/path/to/libdatetime.so` runs the
actual plugin on Xvfb with a private D-Bus and private XDG config/data/cache.
It creates only synthetic local EDS sources. It checks the tabs, undated tasks,
shared event UIDs across calendars, live edits/deletions/completion, and source
enable/disable. It requires `xvfb xauth dbus-daemon` plus the development/runtime
dependencies above. The fixture uses local GIO and disables file-portal activation only in its
private D-Bus session, avoiding temporary document mounts during cleanup.
Expected portal-unavailable warnings do not fail the agenda checks.
Google OAuth and remote round trips require the owner's
Google sign-in and are separate from these local tests.
