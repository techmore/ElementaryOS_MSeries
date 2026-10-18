# Pantheon calendar agenda

The datetime indicator has **Events** and **Tasks** tabs above the calendar's
right pane. Events has **Month**, **Week** and **Day** agenda views. Tasks shows
all incomplete tasks
from selected, enabled elementary Tasks lists, including tasks with no due
date. Dated tasks sort first, then undated tasks alphabetically. Activate a
task to open elementary Tasks; completion and editing stay in that app.

Both tabs use Evolution Data Server (EDS), the native Calendar/Tasks store.
Updates, deletions, source selection and account additions are observed live.
Identical UIDs in separate calendars do not hide each other's events.

## Month, Week and Day views

Choose **Month**, **Week** or **Day** inside Events. The month grid remains a
compact date picker in every mode. Month lists the selected month's events;
Week lists the selected locale-based week; Day shows the selected day's events.
Wider views group rows under date headings, with all-day events before timed
meetings. Multi-day events appear on each day they overlap; all-day end dates
remain exclusive. Recurring instances and separate calendars retain their identities.

Rows show the event title, all-day/time range, calendar name, location and a
short description when available. Titles wrap and descriptions offer a tooltip
for longer text. Calendar colors mark the edge of neutral cards for readable
text in light and dark themes. The event list scrolls inside a bounded pane.

The arrows beside the agenda heading move one month, week or day according to
the selected mode. The arrows above the date grid always browse months.
**Today** selects today's date without changing the agenda mode. Day is the
initial default; the mode is retained while opening/closing the popup in the
same panel process. Tasks remains an independent list of incomplete items.
Event activation opens the native Calendar app on that row's date.

Navigation uses each grid's actual month, rejects stale carousel notifications,
and synchronizes the selected date and its highlight even when focus stays on
a popup control. Returning to Today does not depend on an animated offset.
These are agenda views; no hourly time grid or event editing is added to the panel.

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
It creates only synthetic local EDS sources. Ten workflow groups cover:
Today/highlight/repeated navigation; Day details and literal text; Week and Month
boundaries; recurring/multi-day events; period arrows and year rollover; empty
states and mode retention; independent Tasks; live edits/deletions; and source
changes. Test dates/labels use a fixed C.UTF-8 locale (Sunday-start weeks). It requires `xvfb xauth dbus-daemon` plus the development/runtime
dependencies above. The fixture uses local GIO and disables file-portal activation only in its
private D-Bus session, avoiding temporary document mounts during cleanup.
Expected portal-unavailable warnings do not fail the agenda checks. Set
`AGENDA_TEST_DARK=1` for the dark-mode run and `AGENDA_PREVIEW_DIR=/path/to/dir`
to retain synthetic rendered previews.
Google OAuth and remote round trips require the owner's
Google sign-in and are separate from these local tests.
