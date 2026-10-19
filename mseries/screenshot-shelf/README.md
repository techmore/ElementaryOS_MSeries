# Screenshot shelf and Markup

**Command+Shift+4** (Command is Ctrl on this keyboard) opens the selector: drag to capture an area, or press **Space** to switch to window mode (the window under the pointer is highlighted blue; click to capture it, Space again goes back to dragging) (needs the patched Gala from `install-gala-screen-corners.sh`, active after next login; stock Gala ignores Space). Command+Shift+3 captures the screen.

After a screenshot, a thumbnail appears bottom-right at a fixed size (280x180 card, any screenshot shape) and stays for **4 seconds** (longer while the pointer is on it or you are dragging), so you can drag it into an app.

| You do | What happens |
| --- | --- |
| Drag it into an app | The screenshot is **used, not kept**: its saved file moves to the **Trash** 2 minutes after an accepted drop (recoverable, never hard-deleted). Works with Flatpak apps such as Signal (see below). |
| Press **Copy** | The full image goes on the clipboard; paste it anywhere (Ctrl+V). The file is kept. |
| Hold **Alt** while dragging | The screenshot is used **and a copy is kept**; the thumbnail text changes to "Saving a copy (Alt)". |
| Click it, or press **Markup** | Opens Swappy (the card stays) (arrows, shapes, text, highlight, blur, crop). The result is saved next to the original as `<name> (markup).png`. |
| Click the x | The thumbnail goes away and the screenshot stays in `~/Downloads/Screenshots`. |
| Ignore it | It goes away after 4 seconds. |

A screenshot is only ever moved to the Trash by a drag without Alt, and only after the drop was accepted. A cancelled drag keeps it.

`mseries-markup FILE` also works from the file manager (Open With, Markup): images open in Swappy, PDFs in Papers (which has its own annotations).

Install: `bash mseries/install-screenshot-shelf.sh` (adds `swappy` if missing, starts the shelf, adds a desktop autostart entry). Remove: `--uninstall`. Log: `~/.cache/mseries-screenshot-shelf.log`.

Implementation: a GTK4 helper that watches `~/Pictures/Screenshots` (Gala's save folder, linked to `~/Downloads/Screenshots`), runs through XWayland so it can place itself bottom-right (the launcher uses the same trick), and offers the staged copy as the drag source.

## Checked on the M1 Pro (2026-10-14)

Watcher picks up a new screenshot and shows the thumbnail; an ignored thumbnail expired after 7 seconds in the original version and the file is kept; the card renders correctly offscreen; Swappy starts through the wrapper.

## Not yet checked

Dragging into real apps, Alt detection during a drag, and the thumbnail's exact position on screen. If Alt is not detected, use Markup to keep a copy, or just ignore the thumbnail.

## Recovery and deployment check (2026-10-18)

Reinstall with `bash mseries/install-screenshot-shelf.sh`. The installer writes quoted absolute
Exec paths into the installed desktop entries: `%h` is not a valid desktop field code and prevented
login startup. This also fixes the Markup launcher. Validate with
`desktop-file-validate ~/.config/autostart/mseries-screenshot-shelf.desktop ~/.local/share/applications/mseries-markup.desktop`.
The shelf log is `~/.cache/mseries-screenshot-shelf.log`; after login it should say `watching`.

Build the window picker from this checkout with `bash mseries/install-gala-screen-corners.sh`,
then log out and back in. Confirm the installed binary contains `gala_selection_area_update_hover`
with `strings /usr/local/lib/mseries/gala/bin/gala | rg gala_selection_area_update_hover`.
This checks the installed code, not what the running compositor has loaded.

On 2026-10-18 the installed binary still contained the old click-only picker even after login;
it was rebuilt from main with the Space/highlight patch. Shelf startup is now fixed and a synthetic
Screenshot PNG produced `showing` then `shelf done: expired` four seconds later. Both installed desktop
entries validate. The shutter sound asset exists and event sounds are enabled; audible capture,
Space highlight and drag-out still need a live check after the new Gala loads.

## Flatpak drop targets (Signal) — fixed 2026-10-18

Dragging the card into Signal did nothing, and the screenshot was then deleted. Cause: Signal is a Flatpak
(`org.signal.Signal`) with **no filesystem permission**, so the dropped `file:///run/user/1000/mseries-shelf/...`
path does not exist inside its sandbox. Signal accepted the drop, could not read the file and attached nothing;
the shelf counted the accepted drop as "used" and hard-deleted the original 2 minutes later. Chromium/Electron
does not read `application/vnd.portal.filetransfer`, so GTK's built-in portal handoff does not help it either.

Fix: on drag start the staged copy is exported through the document portal (`org.freedesktop.portal.Documents.Add`,
transient) and granted **read-only to the running Flatpak apps**. The drag offers `/run/user/1000/doc/<id>/<name>`,
the same path inside every granted sandbox and on the host. Cleanup deletes the export (access revoked). The
used original goes to the Trash instead of being deleted, and a **Copy** button offers clipboard paste
(no file access needed).

On this machine the host's portal FUSE mount at `/run/user/1000/doc` had vanished while the portal kept serving
the already-running sandboxes (journal: `bwrap: Can't find source path /run/user/1000/doc/by-app/org.signal.Signal`
when Signal was relaunched). In that state the shelf puts a hard link at the doc path so native apps still get a
readable file. New Flatpak launches stay broken until the portal is restarted (log out and back in, or
`systemctl --user restart xdg-document-portal` while no Flatpak apps are running).

Checked headlessly (Xvfb, 2026-10-18): export readable from inside the running Signal sandbox (`flatpak enter`),
unreadable after cleanup; drag content serializes to `text/uri-list`, `text/plain`, `application/vnd.portal.files`
and `application/vnd.portal.filetransfer`; Copy puts a texture on the clipboard; original lands in the Trash;
card renders with the Copy button. **Not yet checked:** a real hand drag into Signal on the desktop.
