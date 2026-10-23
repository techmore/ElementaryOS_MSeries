# Smart Reply

Click into a chat reply box and press **Ctrl+Alt+R** (physical Command+Option+R where Command is swapped with Ctrl). A
local model drafts a reply from the visible conversation. A notification shows the draft; **Tab** inserts it into the
field, **Esc** (or any other key, or switching focus, or 60 seconds) discards it. It never sends anything.

Feedback is in the message box itself, as underlined composing text: `Drafting… 3s` with a running timer while the model works, then the
draft followed by the keys: `Tab insert · Alt+R reword · Alt+P polite · Alt+C concise · Alt+T think harder (slow) · Alt+= more context · Esc discard`. Tab (or
Enter) inserts only the draft. This is used for GTK and Qt apps; for Chromium and Electron apps (which confirm composing text when
focus moves) the draft appears in a notification instead, with the keys in its title.

**Quick actions** change the draft that is being held, without leaving the message box. They are Alt chords, so they never collide with
typing (the engine only sees keys while a draft is held, and any plain key still abandons the draft):

| Keys | What it asks the model |
| --- | --- |
| Alt+R | Reword: the same thing in different words |
| Alt+P | More polite: warmer, not stiffer or longer |
| Alt+C | More concise: shorter and more direct |
| Alt+T | Think harder: the model's thinking switched on and a larger token budget (1200), slow: expect 30 to 120 seconds with the timer running; the reasoning is stripped before anything is shown. Normal drafts never think |
| Alt+= (or Alt++) | More context: the field shows `Extra context (Enter redrafts · Esc back):` and you type a few words (up to 300 characters; Backspace edits, Esc goes back to the draft); Enter redrafts with them |

Each action shows `Drafting… Ns` again and replaces the draft; if the model fails the old draft comes back with a notification saying
why. The instruction sent is one fixed sentence per action (`mseries_ai::Instruction`), never conversation text; your extra context
is added as your own words. The note you type is a line the input service draws as composing text, so nothing is typed into the app
and nothing needs reading back or cleaning up (no paste or caret movement in it). The input service keeps the conversation lines the
draft answered only while the draft is held (the trigger hands them over with `SetContext`) and forgets them with it. A draft
handed over without a conversation (`Offer`) does not advertise the actions. Design and
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

**Verified:** unit tests (rules, legacy file, bounded walker, gate order with read counts, Tab/Esc state machine, Alt-chord and
note-entry key classification, the fixed instruction list, a fixture run of every action, IBus wire shapes);
`quick-actions-smoke.py` (a private session with its own ibus-daemon, AT-SPI bus and input service, one real GTK 4 entry with
`GTK_IM_MODULE=ibus`, real X key presses: Alt+R/P/C redraft with the local model and Tab inserts the result, Alt+= takes a note and
redrafts with it, Esc in the note keeps the draft, a plain `r` abandons it and is typed, no conversation means no actions); the reader on live Brave (Teams) and Signal windows; the input service on the real ibus-daemon with a test input
context and a GTK entry (Tab commits once, Esc and any other key commit nothing, the previous engine is restored, a
sensitive field is refused). **Not verified:** the quick actions in the owner's own Wayland session and Signal client (only the
private X11 session above); in Chromium/Electron (notification path); a real Command+Option+R press and Tab in the owner's chat apps; Esc and
focus-loss behaviour in Chromium; apps that expose no accessibility tree get no context. No settings panel yet (edit the
JSON).
