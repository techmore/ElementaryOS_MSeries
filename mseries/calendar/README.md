# Pantheon calendar agenda

The datetime indicator has **Events**, **Tasks** and **+** (Bible: a daily
verse and a Titus study) tabs above the calendar's right pane. Events defaults to **Upcoming · next 30 days**, grouped by local
date independently of the left calendar selection. Ended events are omitted;
ongoing events remain visible. **Month**, **Week** and **Day** are available as
explicit alternate views. Tasks shows
all incomplete tasks
from selected, enabled elementary Tasks lists, including tasks with no due
date, in sections: **Overdue**, **Today**, **Tomorrow**, **Next 7 days**,
**Later** and **No due date**. Within a section, tasks sort by due time, then
high-priority tasks (iCalendar priority 1–4, marked **!**), then title. Each row
says when it is due in words ("Overdue since yesterday", "Due today", "Due
Friday"; overdue in red, today in the accent colour), its list, its category
(Homeboard puts the project name there) and **Repeats** for repeating tasks.
The Tasks tab shows a dot while anything is overdue. Wording and sections roll
over each minute while the tab is open. Activate a
task row to open elementary Tasks for editing. Check its checkbox to complete it
directly in the panel; the same EDS record updates in Tasks. The checkbox is
disabled while saving and for read-only/unavailable lists. A failed save restores
it and shows a retry error. Repeating tasks advance using EDS recurrence handling.

Both tabs use Evolution Data Server (EDS), the native Calendar/Tasks store.
Updates, deletions, source selection and account additions are observed live.
Identical UIDs in separate calendars do not hide each other's events.

## Verse of the Day and Titus study (+ tab)

A **Daily | Titus** toggle (styled like the Events view buttons) switches
between the daily verse and a study of Titus. The choice and the study section
are remembered in `~/.config/mseries/verse-of-the-day.ini`.

### Titus study

**Overview** describes the author, recipient, setting, date, themes and an
outline. Nine sections follow the letter's natural breaks (1:1–4, 1:5–9,
1:10–16, 2:1–5, 2:6–10, 2:11–15, 3:1–7, 3:8–11, 3:12–15) and together cover
all 46 verses. Each section shows its WEB passage with small raised verse
numbers, an **Insight** and a **Reflect** question. ◀ ▶ move between sections
("7 of 9"), and **Overview** returns to the start. The link items search for
sermons on the exact passage, and **Copy Passage** copies the reference and
the plain text. Reopening the popup keeps your section, so you can follow a
sermon series week by week.

Insights and questions are original notes in `titus-study.txt` (GPL, like the
patch). The passages come from the WEB, and `build-verses.py` checks that the
sections cover every verse exactly once.

### Daily verse

The **+** tab shows one Bible verse a day under a Granite header. The header's
second line uses the Events wording (**Today · Sunday, October 18**), and the
same ◀ **Today** ▶ control as the calendar browses other days. Today is greyed
out while you're already on today. Reopening the popup always returns to today.

The verse is set a little larger with more line spacing and centered in its
area. Psalm headings (for example "A Psalm by David.") appear as a small
dimmed caption above the verse instead of being run into it. The reference sits
below on the right.

Panel menu items follow:

- **Listen to Sermons** opens a SermonAudio search for the passage.
- **Watch Sermon Videos** opens a YouTube search for sermons on the passage.
- **Read the Full Chapter** opens the passage in context at Bible Gateway (WEB).
- **Copy Verse** copies `“text” — Reference (WEB)` and shows **Copied**
  briefly; the popup stays open.

Links are built from the reference, so they don't go stale. Choosing one closes
the popup and opens the default browser. Nothing is fetched until you click.

The verse is the same all day and changes at local midnight. Feast days have
their own verse, and the header names the day (for example **Christmas Day ·
Friday, December 25**):

| Day | Verse |
| --- | --- |
| New Year’s Day (Jan 1) | Lamentations 3:22–23 |
| Epiphany (Jan 6) | Matthew 2:10–11 |
| Ash Wednesday (Easter − 46) | Joel 2:13 |
| Palm Sunday (Easter − 7) | John 12:12–13 |
| Good Friday (Easter − 2) | Isaiah 53:5 |
| Easter Sunday | Matthew 28:6 |
| Pentecost (Easter + 49) | Acts 2:4 |
| Thanksgiving (US, 4th Thursday of November) | Psalm 100:4–5 |
| Christmas Eve (Dec 24) | Isaiah 9:6 |
| Christmas Day (Dec 25) | Luke 2:10–12 |

Easter is the Western (Gregorian) date, computed for each year. Reserved verses
are marked `@season` in `verse-references.txt` and left out of the random
order. The other 394 verses get a seeded shuffle per year, so a year never
repeats a verse; no state is stored.

Text is the **World English Bible**, public domain (eBible.org). Words are
never changed. Where a verse quotes a speech whose quotation marks open or
close in a neighbouring verse, the reference is widened to include it (23
verses, for example Exodus 14:13–14) when that stays short and reads naturally.
Otherwise an unmatched mark at the very start or end of the excerpt is left
out (35 verses, for example Joshua 1:9), as is usual when quoting a verse.
Eleven verses keep an opening mark after a complete introduction ("He said to
them, “Go into all the world…") because their quotation continues past the
verse; dropping them would lose well-known verses such as Jeremiah 29:11. To change the list, edit `verse-references.txt` (at least 366
entries) and download `engwebp_vpl.zip` and `engwebp_usfm.zip` from
<https://ebible.org/Scriptures/>. Then run
`python3 -I mseries/calendar/build-verses.py engwebp_vpl.txt 20-PSAengwebp.usfm`.
The USFM marks Psalm headings, which the builder moves to a third column; it
stops if a heading doesn't exactly match the start of verse 1. Copy
`daily-verses.tsv` to `data/daily-verses.tsv` in the patched source tree and
regenerate the patch with `git diff -U2 <pin>`. The plugin bundles the list and
`DailyVerse.css` as GResources.

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
description. When the native Calendar client is installed, **Open in Calendar**
opens it on that block's date; otherwise the popover keeps the readable details
and omits that action.
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

## Continuous integration

The **Calendar Events/Tasks/Homeboard agenda** job in `validate-mseries.yml` runs
`mseries/calendar/ci-test-agenda.sh` on an arm64 Ubuntu runner: it builds the pinned
indicator with our patch (Granite 7.7 and the Wingpanel indicator API come from
`mseries/codexbar-wingpanel/probe/ci-build-deps.sh` when the runner lacks them),
compiles the indicator's GSettings schema privately and runs every agenda group.
Locally it reproduces the same run: `bash mseries/calendar/ci-test-agenda.sh /tmp/agenda`.

## Build and install

Upstream: [elementary/panel-datetime](https://github.com/elementary/panel-datetime),
revision `d0b3a703a7efbb5b3040d7be1ccb616eeb919c54`, GPL-3.0-or-later
(repository COPYING; individual files retain their existing notices).
Our changes are `../patches/datetime-agenda-tabs.patch`; the source pin and
artifact path live in `../panel-factory-pins.json`.

Prerequisites: `git meson ninja-build valac pkg-config libwingpanel-9-dev
libgranite-7-dev libgtk-4-dev libadwaita-1-dev libecal2.0-dev
libedataserver1.2-dev libical-dev libjson-glib-dev` plus the installed datetime 2.4.2 package.

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
All 27 workflow groups use synthetic local EDS sources. The verse group checks
the + tab, today's pick from the bundled list, every feast date in 2026–2028
(including Easter-based dates in three years), a Christmas header on screen,
unpadded single-digit dates, plus previous/next/Today
navigation and its Today/Tomorrow/Yesterday wording. It also checks the Psalm
heading caption, Copy Verse (clipboard contents and the Copied confirmation),
the return to today on reopen, and that 2026, 2027 and leap 2028 each show
365/366 different verses, stable across a day (including DST days) and
reshuffled per year. Timetable groups additionally
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

## Homeboard

[Homeboard](https://tasks.stoverparc.org/board/)'s bridge keeps a dedicated
**Homeboard** list in Evolution Data Server, so Homeboard tasks appear in the
Tasks tab like any other list, with due dates, priority and project names; ticking
or adding one here syncs to Homeboard within a few seconds. Install the bridge with
`bash mseries/install-homeboard-sync.sh` (pinned `techmore/homeboard` revision, or
`HOMEBOARD_SOURCE=/path/to/checkout`; `--uninstall` removes it). It installs
without the separate Homeboard indicator, starts in the background at login, is
restarted by the session if it exits, and is started on demand through D-Bus
activation. Re-running the installer after a pin bump replaces the running bridge.
The bridge backs off to at most 15 minutes while Homeboard is unreachable, reports
a locked login keyring instead of waiting on it, and logs counts and failures (never
task text or tokens) to the user journal. Deleting a Homeboard task in Tasks does
not delete it on Homeboard; delete or archive it there. Details:
`linux/README.md` in `techmore/homeboard`.

When the bridge is installed, a **Homeboard** strip sits above the composer:
the last sync ("Synced 12 tasks · 9 open · 2 min ago"), a spinner while syncing,
**Sync now**, **Open Homeboard** and, when signed out, **Sign In…** (Google
sign-in in the browser; the owner's step). The strip reads the bridge's
`~/.local/state/homeboard/panel.json` (no token is ever in it) and asks the
bridge to act through its D-Bus actions (`org.techmore.Homeboard`, `app.sync` /
`app.connect`); D-Bus activation starts the bridge if needed. Without the
bridge the strip stays hidden. Older bridges that publish only a status sentence
are still read.

## Completing tasks in the panel

Checkboxes write to the existing source/UID/recurrence record. Before saving, the
model fetches its latest version so newer edits are preserved. Completion records
use EDS’s recurrence-aware helper, a UTC modification time and an incremented
sequence. Repeated clicks are suppressed while a save is pending; checking a box
does not open Tasks or close the dropdown. Completed tasks leave the incomplete
list; repeating tasks retain their next occurrence. For eight seconds an
**Undo** bar below the list offers to reopen the task (needs-action, 0 %, no
completion time, newer edits kept). Repeating tasks say "next one scheduled"
instead, since their series already advanced; reopen those in Tasks. Editing
remains in the Tasks app. No personal task is changed by the tests.

The private-D-Bus fixture also checks persisted status/percent/timestamp, stale
row edits, identical UIDs in different lists, recurring advancement, and a
missing-record failure with checkbox/error recovery. Further groups check the
sections and their order, overdue/today wording, priority-first order, category
text and the overdue tab dot; Undo restoring the stored record (and the
repeating-task message); the date selector writing an all-day DUE; and the
Homeboard strip (hidden until installed, signed-out and synced states, Sync now
reaching a stand-in `org.techmore.Homeboard` on the private bus, the older status
format). The fixture sets its own `XDG_STATE_HOME`, so the real Homeboard status
is never read.


## Adding tasks in the panel

Type a title in **New task…**, choose a writable **List**, then press Enter or
click **Add**. The selector initially uses the default Tasks list when available
and retains your chosen list while the panel runs; if that list goes away, it
returns to the default list. The date selector beside it offers **No date**,
**Today**, **Tomorrow** and **In a week** (an all-day due date) and resets to
No date after each add. New tasks appear in the same EDS list in elementary
Tasks; use Tasks to add times or details.

Saving disables repeat submission and keeps the dropdown open. Blank titles are
ignored. Failed saves retain the draft and show a retry error; unavailable or
read-only lists cannot receive new tasks. The private fixture checks Enter and
Add, exact list identity, literal Unicode/markup titles, persisted metadata,
duplicate suppression and draft/list recovery when sources become unavailable.
