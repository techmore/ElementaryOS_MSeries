# T3 panel menu: UI/UX and elementary HIG audit (2026-10-27)

Scope: the unified T3 Wingpanel indicator (`mseries/t3-wingpanel/Indicator.vala`) and the
menu it hosts, `mseries/dock-taskbar/TaskbarT3RPopover.vala`, which embeds the CodexBar
(`mseries/codexbar-wingpanel/Indicator.vala`) and RepoBar widgets as its Usage and GitHub tabs.
The same menu also opens from the dock, so every fix here lands in both places.

Evidence: source reading plus fixture screenshots in light and dark
(`receipts/2026-10-27-hig-audit/`, before on the left, after on the right). Not checked: a live
Wingpanel load, real keyboard focus order in the panel, or a screen reader.

Line numbers refer to `origin/dev` after the fix PR unless marked.

## Fixed in this PR

| # | Finding | Where | Fix |
|---|---------|-------|-----|
| F1 | **Plan windows and threads were hidden.** Both lists sat in their own scroll area inside the menu's scroll area. GTK gave them almost no height, so only the first plan window showed (its gauge cut off) and the second thread never appeared. A 92 % weekly window was invisible. | `TaskbarT3RPopover.vala` usage/activity scrollers (were lines 139–159) | Removed the inner scrollers; the menu itself scrolls. |
| F2 | **The menu changed width on every tab switch** (512 → 416 → 488 px), so the popover jumped under the pointer. | `TaskbarT3RPopover.vala:71` (`hhomogeneous = false`) | One width for all tabs (`hhomogeneous = true`). |
| F3 | **Idle tooltip said "T3 · 0 running".** The accessible name never changed after start-up, so a screen reader always heard "Usage, GitHub, Activity and Fleet", never the status. | `t3-wingpanel/Indicator.vala:18–30` | Native two-line Granite tooltip (`T3` / status in secondary text), "Idle" when nothing runs, correct plurals, and the same text as the accessible name. |
| F4 | **Unreadable numbers.** "18436221 tokens", "$41.2873 USD", and a raw "read 2026-10-27T23:38:48.929679Z" timestamp. | `render_tokens` | Digit grouping (18,436,221), cents ($41.29), relative time ("read just now"). |
| F5 | **Two different things called "Activity".** The thread list heading and the footer button (which opens Shiplog) shared one name. | thread list heading | Heading renamed to "Threads". |
| F6 | **Machine-style wording.** "2 request(s)", "1 active item(s)", "Tokens · provider total" plus a two-line repeat of the same scope, and "· Model: claude-opus-…" truncating every thread subtitle. | `append_thread`, `render_activity`, token card | Real plurals, "Tokens" heading with one scope line ("Claude · all accounts, not just the selected one"), model moved to the row tooltip. |

## Owner-approved layout changes (H1–H5, done)

The owner approved these the same day; they are in the same PR.

| # | Was | Now |
|---|-----|-----|
| H1 | Two stacked tab bars on the Usage tab (Usage/T3 server/GitHub, then Quota/Sessions/Spend) and three button rows. | One tab bar. Embedded CodexBar shows Quota only (its switcher is hidden when `on_demand`); Sessions and Spend open from its Usage details / Spending details buttons. The footer is a separator and plain menu items: Open T3, Activity, Fleet, then a separator and "T3 Settings…". The duplicate Usage / Repositories buttons are gone (M2). |
| H2 | 36 px icons in the embedded CodexBar row. | 16 px when embedded (`dock_icon_size ()`); the standalone double-size dropdown keeps 36 px. Its 300 px minimum height is also dropped when embedded. |
| H3 | Menu text at 1.2em. | System text size, like Sound and Network. |
| H4 | Blue suggested-action "Open T3" button. | Plain menu item (`Granite.STYLE_CLASS_MENUITEM` + `flat`). |
| H5 | Badge showed the running-thread count. | Badge only for approvals waiting; running work shows in the tooltip only. |

The GitHub tab's Dashboard / Pinned / Attention / All row is a list filter, not page navigation, so it stays.

## Still open

### Medium

**M1. The default tab is Usage, which needs CodexBar to be signed in.** When it is not (fixture,
fresh install), the menu opens to "No quota data yet" with a centred 64 px icon, even when T3 is
live with threads waiting. Fix: open on "T3 server" (status first), or switch to it when a thread
needs approval.

**M2. (Done with H1.) Duplicate actions.** The row "Usage / Repositories / Settings" on the T3 server tab opens app
pages that duplicate the Usage and GitHub tabs one click above. Fix: drop "Usage" and
"Repositories"; keep "Settings…" (with an ellipsis, because it opens a window) as a menu item.

**M3. Naming drifts:** "T3-R Pantheon" (header), "T3" (tooltip, Open T3), "T3-R application"
(error text), "RepoBar"/"CodexBar" inside user-facing strings ("…no repositories RepoBar can read").
Fix: one product name in the UI; internal component names stay out of copy.

**M4. Full-colour 28 px app icon and title header** on the server tab
(`TaskbarT3RPopover.vala:86–105`). Wingpanel menus have no app header; the panel icon already says
which menu this is. Fix: drop the header and lead with the connection line and account.

**M5. Forced minimum height of 420 px** in hosted mode (`TaskbarT3RPopover.vala:194`) leaves
blank space under short pages (GitHub empty state). Fix: let the popover size to content up to the
640 px cap.

**M6. Opening a thread spawns the binary directly** (`TaskbarT3RPopover.vala:693`) without a launch
context, so there is no startup feedback and focus may not move to the app. Fix: activate the
app's `open-thread` action through `DesktopAppInfo`/`GApplication` with the display launch context,
as `run_action` already does.

**M7. Thread rows have no visual affordance** beyond a flat button; the pending state relies on
colour alone (`warning` class). The text "Needs approval" carries meaning, so this is acceptable,
but an `dialog-warning-symbolic` 16 px icon at the start of pending rows would match how elementary
marks attention.

### Low

**L1. No translation setup.** Strings are plain literals; there is no gettext domain. Already noted
in `README.md`. Fix when the panel is packaged: wrap in `_()` and add `po/`.

**L2. Deprecated API.** `Granite.STYLE_CLASS_MENU` (`TaskbarT3RPopover.vala:57`, deprecated in
Granite 7.7 in favour of `Gtk.PopoverMenu`) and `Gtk.StyleContext.add_provider_for_display`.
Harmless today; migrate with the H1 rework.

**L3. Custom card styling** (`alpha(currentColor, 0.045)` backgrounds, 10 px radius,
`TaskbarT3RPopover.vala:368–373`) reads fine in both schemes (checked in screenshots) but is a
local look. Granite's `card` style class would follow the system theme and accent automatically.

**L4. Dates as ISO days** ("2026-10-21 – 2026-10-27"). A locale date ("Oct 21 – 27") is easier to
read.

## What is already right

- Symbolic panel icon, recoloured by the panel in light and dark.
- Gauges use theme semantic colours (success / warning / error), not hard-coded hex.
- Stale and offline states keep last-known data with an age and say how to recover.
- No polling while closed; Escape and outside click are owned by Wingpanel.
- Wrapping and ellipsizing are set on dynamic labels.
