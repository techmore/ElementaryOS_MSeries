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
draft answered only while the draft is held (the trigger hands them over with `SetContext`, together with the personal notes the first draft used, so a revision is written with the same knowledge) and forgets them with it. A draft
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
- `memory add|list|edit|rm|export|preview` manages the persona records described below.
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

## Persona and what it knows about you

Drafts are written by the owner's helpful chat assistant: it writes the message **you** would send, in your voice. To sound like
you and know your people it is given a few records that **you** wrote, kept in the same owner-only database as the other AI
settings (`$XDG_DATA_HOME/mseries-ai/assistant.sqlite3`). Nothing is learned automatically and nothing leaves the machine.

```bash
mseries-reply memory add profile "I'm Sean. I run a small manufacturing shop; I text in a dry, friendly way."
mseries-reply memory add style "Short messages, lowercase is fine, no emoji."
mseries-reply memory add contact "Sam Example" --alias Sammy --relationship brother --tone "teasing, relaxed" --notes "Lives in Denver."
mseries-reply memory add topic "Planning a gravel ride in Moab the first weekend of May." --title "Moab ride" --keywords ride,moab --contact Sammy
mseries-reply memory add fact "The shop is closed on Fridays in summer." --keywords friday,closed
mseries-reply memory list            # ids: c1 contact, n3 note, m2 saved memory
mseries-reply memory edit n3 --text "Ride moved to June."
mseries-reply memory rm c1           # removing a contact removes its notes
mseries-reply memory export notes.json
mseries-reply memory preview --contact "Sam Example" "are you in for the ride?"
```

- A **contact** is matched when the chat's title/header contains its name or an alias (whole words, ignoring case). If two
  different contacts match (a group chat), none is used. Profile and style notes are always considered; a **topic** or
  **fact** is used when one of its keywords (or its title, if it has no keywords) appears in the title or the last six messages,
  or when it is linked to the contact the chat is with.
- At most **1,400 characters** of records go into one prompt, most important first (the contact, who you are, how you write,
  topics, facts, older memories), so drafts stay quick on the 4B model.
- Privacy: records are read only after the rules allowed the app, the field and the contact, and are also checked against your
  contact block rules under every name the contact has, so a blocked contact is never read. Record text is treated as data: it
  is never part of the instructions the model is given. The model still has no tools. The audit line (`personal` in the journal)
  shows only counts. The quick actions above use the same notes. `trigger --dry-run` and `memory preview` print the records that would be used, to your terminal.
- There is no settings panel for this yet; the command is the way to manage it. The database schema moved to version 2, so
  other M-Series apps that share it (Messages) must be rebuilt together with this one.

**Verified:** unit tests (rules, legacy file, bounded walker, gate order with read counts, Tab/Esc state machine, Alt-chord and
note-entry key classification, the fixed instruction list, a fixture run of every action, IBus wire shapes);
`quick-actions-smoke.py` (a private session with its own ibus-daemon, AT-SPI bus and input service, one real GTK 4 entry with
`GTK_IM_MODULE=ibus`, real X key presses: Alt+R/P/C redraft with the local model and Tab inserts the result, Alt+= takes a note and
redrafts with it, Esc in the note keeps the draft, a plain `r` abandons it and is typed, no conversation means no actions); the reader on live Brave (Teams) and Signal windows; the input service on the real ibus-daemon with a test input
context and a GTK entry (Tab commits once, Esc and any other key commit nothing, the previous engine is restored, a
sensitive field is refused). **Not verified:** the quick actions in the owner's own Wayland session and Signal client (only the
private X11 session above); in Chromium/Electron (notification path); a real Command+Option+R press and Tab in the owner's chat apps; Esc and
focus-loss behaviour in Chromium; apps that expose no accessibility tree get no context. No settings panel yet (edit the
JSON; use `memory` for the personal records). The persona, retrieval and `memory` command have unit tests (retrieval matching and
budget, a blocked contact reads no record, hostile record text cannot change the system prompt, the audit holds counts only) and
one live draft against the local model with a throwaway database; whether the records measurably improve drafts has not been scored.
