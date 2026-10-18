# Screenshot shelf and Markup

**Command+Shift+4** (Command is Ctrl on this keyboard) opens the selector: drag to capture an area, or just **click a window** to capture that window (needs the patched Gala from `install-gala-screen-corners.sh`, active after next login; stock Gala treats a click as cancel). Command+Shift+3 captures the screen.

After a screenshot, a thumbnail appears bottom-right at a fixed size (280x180 card, any screenshot shape) and **stays** until you dismiss it, drag it away or take the next shot.

| You do | What happens |
| --- | --- |
| Drag it into an app | The screenshot is **used, not kept**: its saved file is deleted 2 minutes after an accepted drop. |
| Hold **Alt** while dragging | The screenshot is used **and a copy is kept**; the thumbnail text changes to "Saving a copy (Alt)". |
| Click it, or press **Markup** | Opens Swappy (the card stays) (arrows, shapes, text, highlight, blur, crop). The result is saved next to the original as `<name> (markup).png`. |
| Click the x | The thumbnail goes away and the screenshot stays in `~/Downloads/Screenshots`. |
| Ignore it | It stays where it is; the next screenshot replaces it. |

A screenshot is only ever deleted by a drag without Alt, and only after the drop was accepted. A cancelled drag keeps it.

`mseries-markup FILE` also works from the file manager (Open With, Markup): images open in Swappy, PDFs in Papers (which has its own annotations).

Install: `bash mseries/install-screenshot-shelf.sh` (adds `swappy` if missing, starts the shelf, adds a desktop autostart entry). Remove: `--uninstall`. Log: `~/.cache/mseries-screenshot-shelf.log`.

Implementation: a GTK4 helper that watches `~/Pictures/Screenshots` (Gala's save folder, linked to `~/Downloads/Screenshots`), runs through XWayland so it can place itself bottom-right (the launcher uses the same trick), and offers the staged copy as the drag source.

## Checked on the M1 Pro (2026-10-14)

Watcher picks up a new screenshot and shows the thumbnail; an ignored thumbnail expires after 7 seconds and the file is kept; the card renders correctly offscreen; Swappy starts through the wrapper.

## Not yet checked

Dragging into real apps, Alt detection during a drag, and the thumbnail's exact position on screen. If Alt is not detected, use Markup to keep a copy, or just ignore the thumbnail.
