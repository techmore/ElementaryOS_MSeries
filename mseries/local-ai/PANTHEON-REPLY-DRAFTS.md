# Shared local AI reply drafts for Pantheon apps

## First consumer

The Rust Messages app can request a reply draft from the existing local Qwen
service at `http://127.0.0.1:8766/v1`. It makes a request only after the user
chooses **Draft reply**, checks that a supported Qwen model is already loaded,
and never starts or switches an inference worker. The current conversation's
last 12 messages are sent to that loopback endpoint, with a 12,000-character
context cap. Context is held in memory for the request and is not written to
SQLite.

The composer shows a spinner and **Thinking…** while the model works. A
returned suggestion appears in a preview. **Insert (Tab)** or Tab inserts it at
the composer cursor; **Discard** removes it. Insertion never sends. A
conversation switch or a change to the recent history discards a stale result.
Generation is bounded to 120 seconds. The current client waits for the complete
reply rather than displaying partial model tokens.

## Shared storage

All app integrations use `mseries-ai` and the same user database at
`$XDG_DATA_HOME/mseries-ai/assistant.sqlite3` (or
`~/.local/share/mseries-ai/assistant.sqlite3` when `XDG_DATA_HOME` is unset).
The directory and database use owner-only permissions; SQLite uses WAL mode
and a busy timeout for concurrent app access.

The database stores a loopback model endpoint, app-scoped writing preferences,
and explicitly saved memories. The Messages menu's **AI Reply Drafts…** page
edits the endpoint, Messages writing guidance, shared-memory use, and Messages
or shared memories. Other apps can read shared memories and manage their own
app-scoped memories through the same crate. A memory can be scoped to one app
or to `*` for intentional sharing across apps. Conversation text, generated
drafts, and memories inferred by the model are never saved automatically.
Memories are plain text in the local owner-only database.

The endpoint must be HTTP on localhost or a loopback IP, with no credentials,
query string, or fragment. Requests bypass proxy environment settings. If the
service is unavailable, the app explains that the local model needs to be
loaded; it does not fall back to a remote provider.

## App boundary

`mseries-ai` is a reusable app-side crate, not a second model server. Each app
adapter decides what context the user has selected and passes bounded text to
the shared client. The shared database supplies preferences and explicit
memories without turning conversation history into a cross-app transcript.

Messages is the first adapter because the Rust frontend already owns a
supported BlueFerry-backed composer. Signal remains on its signed official
client until Signal publishes a supported compose/API boundary. Signal's
official `libsignal` project says use outside Signal is unsupported, so this
feature does not read Signal's private profile/database or patch its Electron
application. The requested tabbed agent window depends on adapters with
supported context and compose boundaries; Messages can use BlueFerry, while
Signal remains gated on its official API.

## Next steps

- Reuse the crate in other apps that have a clear user-selected text/context
  boundary.
- Extract shared settings widgets only when a second app adapter needs them;
  the database API is already reusable across apps.
- Build the tabbed agent window around supported app adapters; add Signal only
  if an official Signal API becomes available.
- Capture light/dark and narrow-window states, then qualify Tab insertion and
  local-model availability in an isolated runtime.
