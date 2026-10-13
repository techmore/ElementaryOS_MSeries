# Changelog

## 2026-10-13

### Network indicator
- **Added** live download and upload speed with a 60-second graph, measured across physical interfaces only.
- **Added** a collapsible **Network Usage** section with Apps, Hosts and DNS tabs over Today, 7 days and 30 days. It reads the database only while open.
- **Added** drill-down: click an app to see its hosts, or a host to see which apps used it, with a back row to return.
- **Changed** the Wi-Fi list to show only the connected network, with a chevron to reveal the rest. It collapses again when the popover closes and shows everything when you are not connected.

### Usage logger (`netusage`)
- **Added** a user service that records per-process and per-host TCP usage plus DNS lookup counts to SQLite, polling every 5 seconds and skipping idle periods. Capped at 10% CPU and 96 MB, with built-in retention (2 days of minutes, 90 days of hours).
- **Known limit:** UDP/QUIC traffic is not attributed to apps.

### Local Troubleshooter
- **Changed** reports to plain language: a one-sentence verdict, **Needs attention** with a **Fix:** per item, and **Fine to ignore**. Answers stay under about 200 words and no longer end with a long list of commands.
- **Added** auto-sorting so items whose fix is "nothing to do" move to *Fine to ignore* and duplicates are removed. Also applies to previously saved reports.
- **Changed** the evidence given to the model: repeated lines collapse, known-harmless noise is dropped, and crashes show their age. The prompt now forbids inventing commands or guessing causes.
- **Changed** the window to use native elementary widgets: the question lives in the title bar, one menu holds the options and tools, a Granite placeholder offers starter questions, and confirmations appear as toasts. Reports render as formatted text with the evidence behind a switch.
- **Added** a Cancel button, a progress screen with elapsed time, and background loading for the checklist so the window no longer freezes.
- **Added** crash notifications from the watcher, with an **Analyze** button or a "diagnosis ready" follow-up. Disable with `~/.local/state/mseries-troubleshooter/no-notify`.
- **Added** an app icon and a launcher named after the app ID (`org.techmore.MSeries.Troubleshooter`) so the dock, notifications and window match.
- **Fixed** "Run checks now" freezing the window for up to two minutes.

### Docs
- **Added** README and screenshots of the Local Troubleshooter in both light and dark themes.
