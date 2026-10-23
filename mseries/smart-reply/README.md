# Smart Reply

Click into a chat reply box and press **Ctrl+Alt+R** (physical Command+Option+R where Command is swapped with Ctrl). A
local model drafts a reply from the visible conversation. A notification shows the draft; **Tab** inserts it into the
field, **Esc** (or any other key, or switching focus, or 60 seconds) discards it. It never sends anything.

Feedback is in the message box itself, as underlined composing text: `Drafting… 3s` with a running timer while the model works, then the
draft followed by `— Tab inserts, Esc discards`. Tab inserts only the draft. This is used for GTK and Qt apps; for Chromium and
Electron apps (which confirm composing text when focus moves) the draft appears in a notification instead. Design and
limits: [SMART-REPLY-DESIGN.md](../SMART-REPLY-DESIGN.md).

The implementation is the Rust crate [`rust/mseries-reply`](../../rust/mseries-reply); this folder holds the systemd unit
and this note. Install with `bash mseries/install-smart-reply.sh` (per user, no sudo; builds the crate; replaces the
earlier Python bridge in place); remove with `--uninstall`. It needs the local model on `http://127.0.0.1:8766/v1`
(loopback only, through `mseries-ai`, never a remote provider).

`mseries-reply` subcommands:

- `trigger [--in SECONDS] [--dry-run]` is what the shortcut runs. It asks the compositor (`org.pantheon.gala`
  `GetWindows`) which window has focus, applies the rules, reads the window through AT-SPI (bounded: 1.2 s, 2500 nodes,
  the message box plus the text above it, newest kept), asks the model, and hands the draft to the input service.
  `--dry-run` prints the decision and the context without calling the model.
- `input-service` is the IBus engine service (`org.techmore.SmartReplyInput`, unit `mseries-smart-reply-input.service`).
  It refuses password and unknown fields with the same checks as the F5 dictation input, holds one draft, commits it on
  Tab, and restores the previous input method. F5 dictation is untouched.
- `init-rules` writes the default rules file unless one exists. `probe [TITLE]` shows what the reader finds in a window
  (counts only, no message text). `rules`, `packet` and `draft` work on fixtures.

Rules live in `~/.config/mseries/smart-reply.json`. The format of the first slice still works unchanged: `policy`
`allow-list` (default; only listed chat apps) or `block-list`; `apps.allow`/`apps.block` by app id; `contacts.block` by text
in the window title. The newer format (`rules` list with app, contact and field-kind scopes, context caps) works too; see
`rust/mseries-reply/src/rules.rs`. A chat app is one that carries `X-MSeries-Chat=true` in its desktop entry **or** one the
rules file allows by name. Terminals and password managers are always blocked, and a missing, malformed or
group/other-writable file blocks everything. The model gets no tools and is told the conversation is data, not
instructions. The `style` and `endpoint` keys of the old file are ignored: style and endpoint now come from `mseries-ai`.

Chat bubbles in the accessibility tree are followed by a footer line (`09:14 · Delivered`, `09:13 · +1555… · Disappears in 3600 s`). The reader
treats those as who-wrote-it markers, not as messages: a delivery status marks the message before it as yours, anything else as the
contact's.

**Verified:** unit tests (rules, legacy file, bounded walker, gate order with read counts, Tab/Esc state machine, IBus wire
shapes); the reader on live Brave (Teams) and Signal windows; the input service on the real ibus-daemon with a test input
context and a GTK entry (Tab commits once, Esc and any other key commit nothing, the previous engine is restored, a
sensitive field is refused). **Not verified:** a real Command+Option+R press and Tab in the owner's chat apps; Esc and
focus-loss behaviour in Chromium; apps that expose no accessibility tree get no context. No settings panel yet (edit the
JSON).
