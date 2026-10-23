# Smart Reply (first slice)

Click into a chat reply box and press **Ctrl+Alt+R**. A local model drafts a reply from the visible conversation.
A notification shows the draft; **Tab** inserts it into the field, **Esc** (or any other key, or switching
focus) discards it. It never sends anything. Design and limits: [SMART-REPLY-DESIGN.md](../SMART-REPLY-DESIGN.md).

Install with `bash mseries/install-smart-reply.sh` (per user, no sudo); remove with `--uninstall`.
Needs the dictation input method installed (it reuses its field-safety checks) and the local model on
`http://127.0.0.1:8766/v1` (loopback only, never a remote provider).

- `mseries-smart-reply` reads the focused window through AT-SPI (bounded), applies the rules, asks the model, hands the draft over.
  `--dry-run` prints the decision and the context without calling the model; `--in 5` waits 5 seconds first.
- `smart-reply-input.py` is a small IBus engine service (`org.techmore.SmartReplyInput`). It refuses password and
  unknown fields, holds one draft for at most 60 seconds, commits it on Tab, and restores your previous input method.
  F5 dictation is untouched.
- `smart_reply_core.py` holds the rules, prompt, model client and draft cleanup. `python3 -m pytest mseries/smart-reply` runs 16 tests.

Rules live in `~/.config/mseries/smart-reply.json`: `policy` `allow-list` (default; only listed chat apps) or
`block-list`; `apps.allow`/`apps.block` by app id; `contacts.block` by name in the window title. Terminals and password
managers are always blocked, and a missing field or malformed file blocks everything. The model gets no tools and is told
the conversation is data, not instructions.

**Verified:** 16 unit tests; the window reader on a live Teams window; a live draft from the local model (about 10 s).
**Not verified:** the Tab insertion in a running app; Esc and focus-loss behaviour in Chromium; apps that expose no
accessibility tree get no context. No settings panel yet (edit the JSON).
