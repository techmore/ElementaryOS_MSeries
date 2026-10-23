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
  shows only counts. `trigger --dry-run` and `memory preview` print the records that would be used, to your terminal.
- There is no settings panel for this yet; the command is the way to manage it. The database schema moved to version 2, so
  other M-Series apps that share it (Messages) must be rebuilt together with this one.

**Verified:** unit tests (rules, legacy file, bounded walker, gate order with read counts, Tab/Esc state machine, IBus wire
shapes); the reader on live Brave (Teams) and Signal windows; the input service on the real ibus-daemon with a test input
context and a GTK entry (Tab commits once, Esc and any other key commit nothing, the previous engine is restored, a
sensitive field is refused). **Not verified:** a real Command+Option+R press and Tab in the owner's chat apps; Esc and
focus-loss behaviour in Chromium; apps that expose no accessibility tree get no context. No settings panel yet (edit the
JSON; use `memory` for the personal records). The persona, retrieval and `memory` command have unit tests (retrieval matching and
budget, a blocked contact reads no record, hostile record text cannot change the system prompt, the audit holds counts only) and
one live draft against the local model with a throwaway database; whether the records measurably improve drafts has not been scored.
