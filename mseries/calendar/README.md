# Pantheon calendar agenda

The datetime indicator has **Events** and **Tasks** tabs above the calendar's
right pane. Events defaults to **Upcoming · next 30 days**, grouped by local
date independently of the left calendar selection. Ended events are omitted;
ongoing events remain visible. **Month**, **Week** and **Day** are available as
explicit alternate views. Tasks shows
all incomplete tasks
from selected, enabled elementary Tasks lists, including tasks with no due
date. Dated tasks sort first, then undated tasks alphabetically. Activate a
task row to open elementary Tasks for editing. Check its checkbox to complete it
directly in the panel; the same EDS record updates in Tasks. The checkbox is
disabled while saving and for read-only/unavailable lists. A failed save restores
it and shows a retry error. Repeating tasks advance using EDS recurrence handling.

Both tabs use Evolution Data Server (EDS), the native Calendar/Tasks store.
Updates, deletions, source selection and account additions are observed live.
Identical UIDs in separate calendars do not hide each other's events.

<a id="month-navigation-and-today"></a>

## Month, Week and Day views

Choose **Week** or **Day** for time slots with event blocks. Day shows one
column beside the date picker; Week uses the popup width for seven date columns.
Hour and half-hour lines cover the whole local day. Scroll vertically to reach
other hours; busy weeks can scroll horizontally, keeping headers, all-day blocks
and timed columns aligned. The all-day band has its own bounded scrolling area.

Timed blocks follow their start time and duration. Simultaneous events share
side-by-side lanes; touching events reclaim the full column. Very short events
keep a minimum click target and reserve enough lane space to avoid covering
nearby blocks. A short block ending at midnight stays clipped to that boundary.
Overnight events split at local midnight, while all-day end dates stay exclusive.
Recurring instances and separate calendar identities are preserved. Events with
an explicit iCalendar DURATION are supported as well as DTEND.

Click a block for its full title, time range/time zones, calendar, location and
description. **Open in Calendar** opens the native app on that block's date.
These views read calendar data; editing remains in the Calendar app. Labels use
plain text, including descriptions and locations containing markup characters.
The grid uses local wall-clock hours; repeated DST-hour intervals retain a
positive elapsed duration and their exact time zones in the details.

**Month** and the default **Upcoming** keep their compact, expandable lists.
Task rows remain independent. The arrows beside the heading move one month,
week or day in the selected mode. **Today** keeps the mode and selects today's
date. The month-picker arrows and touch swipes browse months; returning to the
picker does not depend on asynchronous carousel notifications. The chosen mode
is retained while reopening the popup in the same panel process.

Live updates reflow blocks and retain the reading position. The Upcoming view
continues to use its separate rolling 30-day EDS model and minute refresh timer.

## Google Calendar

Choose **Calendar Accounts…**, add **Google**, complete the browser sign-in and
consent, and enable **Calendar**. The launcher opens GNOME Online Accounts via
GNOME Settings (with a process-local desktop override), or the standalone GTK
account frontend if Settings is unavailable. EDS discovers Google calendars
from that account and supplies them to Events. The account frontend, EDS and
Tasks are included in the Apple Silicon image dependency list. Factory images use
`gnome-online-accounts-gtk`: elementary deliberately excludes `gnome-control-center`
through its APT policy. Existing desktops with GNOME Settings can keep using it.

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
It creates only synthetic local EDS sources. Timetable workflow groups additionally
check actual block positions against hour rules, overlap geometry, adjacent and
short events, instant/DURATION events, overnight clipping, recurring week columns,
live reflow and scroll retention, and a stubbed native Calendar date action.
Existing workflow groups cover:
Today/highlight/repeated navigation; Day details and literal text; Week and Month
boundaries; recurring/multi-day events; period arrows and year rollover; empty
states and mode retention; independent Tasks; live edits/deletions; and source
changes. Test dates/labels use a fixed C.UTF-8 locale (Sunday-start weeks). It requires `xvfb xauth dbus-daemon` plus the development/runtime
dependencies above. The fixture uses local GIO and disables file-portal activation only in its
private D-Bus session, avoiding temporary document mounts during cleanup.
GTK criticals are fatal in this fixture. The Calendar launcher is a temporary
stub, so testing its date argument opens no real app. Expected portal-unavailable
warnings do not fail the agenda checks. Set
`AGENDA_TEST_DARK=1` for the dark-mode run and `AGENDA_PREVIEW_DIR=/path/to/dir`
to retain synthetic rendered previews.
Google OAuth and remote round trips require the owner's
Google sign-in and are separate from these local tests.

## Completing tasks in the panel

Checkboxes write to the existing source/UID/recurrence record. Before saving, the
model fetches its latest version so newer edits are preserved. Completion records
use EDS’s recurrence-aware helper, a UTC modification time and an incremented
sequence. Repeated clicks are suppressed while a save is pending; checking a box
does not open Tasks or close the dropdown. Completed tasks leave the incomplete
list; repeating tasks retain their next occurrence. Undo/reopening and editing
remain available in the Tasks app. No personal task is changed by the tests.

The private-D-Bus fixture also checks persisted status/percent/timestamp, stale
row edits, identical UIDs in different lists, recurring advancement, and a
missing-record failure with checkbox/error recovery.
