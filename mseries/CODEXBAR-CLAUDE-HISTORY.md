# Claude Code context across account switches

Claude Code's transcript files remain in `~/.claude/projects/<project>/<cli-session-id>.jsonl` when the desktop
account changes. Its Code sidebar is a separate index in
`~/.config/Claude/claude-code-sessions/<account>/<organization>/local_<session-id>.json`.
A different sign-in reads a different index, which hides work that is still on the machine.
This feature restores local **Code-tab** conversations. Regular Chat-tab, Cowork, SSH, WSL and cloud sessions
have different storage/ownership rules and are not migrated by this helper.

## What Switch does

1. Validate the selected saved app login and destination organization before closing Claude.
2. Close Claude, allow its final writes to finish, and save the departing app sign-in.
3. Export the departing account's resumable local Code records and transcript bytes into a private backup.
4. Restore the selected app login. Register missing Code entries in that account's selected organization.
   If a transcript disappeared during the switch, restore its verified export only when its path is absent.
5. Switch the CLI login when requested, then reopen Claude. The result reports how many conversations were added,
   already existed, or could not carry over.

First-time **Set up app sign-in** prepares the selected account's index before reopening Claude at sign-in.
The login screen still requires signing into that selected account once. Ordinary fast switching uses the saved
app login without revoking the old session on the server. CodexBar stays running throughout.

Indexes retain the conversation ID, CLI transcript ID and workspace/worktree paths, so resuming can continue the
same local history. Existing destination records and transcripts are never overwritten, even if their timestamps
look older. Duplicate CLI IDs count as already present. No new prompt is sent automatically; when the owner resumes
and sends a message, that conversation context is processed using the newly selected Claude account.

Only conversation and workspace fields are carried. Old connector configuration, browser/tool permission grants,
queued actions, process IDs and remote-control state are not copied. Imported records start in the default
permission mode, as with a fresh native import. Workspace files themselves remain where they are; this does not
re-create a deleted worktree or fabricate a chat whose local transcript is missing.

## Exports and recovery

Exports live under `~/.local/share/codexbar-claude-app/code-history/` (or the equivalent XDG data directory):

- `export-<timestamp>-<id>/manifest.json`: source/target account IDs, organization, sanitized resume records,
  relative transcript locations and SHA-256 checksums.
- `transcripts/<sha256>.jsonl`: private transcript backups reused by unchanged exports.

Directories are private (`0700`) and files are `0600`. Backups are kept; this version does not automatically prune
history exports. Changed transcripts produce new blobs. No transcript text or authentication material is printed,
and this module does not read cookies or make network requests. Exports stay outside the repository.

`python3 ~/.local/lib/codexbar-cli/codexbar-claude.py history-preview <saved-account-number>` is read-only: it reports
exportable, missing, existing and unavailable counts without signing out or exporting anything. The history module's
`export_history` / `import_missing` functions are exercised by `test-codexbar-claude-history.py`; actual mutations are
coordinated by the app lock in `codexbar-claude.py` after the desktop app exits. Do not manually import while Claude
is running, since it caches its sidebar and could rewrite records.

Export/import failures restore the previous app sign-in before relaunching and do not change the CLI account.
A failed multi-entry import removes only index entries it created; backups and restored transcript bytes remain
recoverable. If CLI switching itself fails after history was prepared, those additive target entries remain ready
for a retry. Neither failure path deletes the original account's history.

## Evidence and limits — 2026-10-18

- Inspected installed Claude Desktop **2.42304.0**; `app.asar` SHA-256
  `fe339c9f7d881b0dfe945bed9f658d97a3e87eba0798e2848fd7a5b9c1b56484`.
  Its local session loader reads the account/org directory and restores `sessionId`, `cliSessionId`, `cwd`,
  workspace anchors and transcript context. Its native external import also creates a reduced session record.
  This was local inspection only; no proprietary bundle code is redistributed in this repository.
- Anthropic documents [local transcripts and separate surface session lists](https://code.claude.com/docs/en/sessions)
  and [resuming a CLI conversation in Desktop](https://code.claude.com/docs/en/desktop#coming-from-the-cli).
- Read-only inspection found 38 local Code entries across two accounts, with all 38 transcript files present.
- Isolated rehearsal using temporary copies of those records/transcripts: forward import added 34; a repeat added
  zero; reverse import added four and preserved the existing 34. Export/import work took about 0.3 seconds.
  The live profile was not written and no provider request was sent.
- Automated tests cover duplicate protection, organization selection, transcript recovery/checksums, private exports,
  unsupported sessions, path/symlink rejection, rollback, and close/export/import/CLI/reopen ordering.
- **Unverified:** a real desktop account switch and opening a carried conversation in Claude. The owner should next
  switch once, select a previous local Code conversation and verify that its workspace and earlier context resume.
  Re-check this private on-disk format after a Claude Desktop update; the upstream CodexBar pin remains **v0.77.0**.

## Live qualification — 2026-10-18

Owner-authorized account1→account2 desktop/CLI switch closed and reopened the
actual app.34 Code conversations carried over: nine active and25 archived.
All transcript/workspace bindings verified on disk, and the running app logged
loading the exact destination index (13 active including four preexisting,25
deferred archived). Owner confirmed the correct account and working Code context.
The app can initially keep its destination account's existing conversation open;
select a carried-over conversation in Code to continue its own transcript.
Automatic view selection is not part of the qualified behavior.

## Pre-switch handoffs and GitHub backup

An account switch prepares a private brief for the most recently focused active
Code conversation before changing authentication. It summarizes bounded recent
visible transcript text; hidden thinking and signatures are excluded. Generation
uses the departing account's Claude Code CLI in safe mode with tools, MCP, hooks,
skills and persistence disabled. If that login is unavailable/mismatched, quota is
exhausted or generation times out, the handoff is labeled emergency excerpts.
Original transcripts are not edited. A new Handoff conversation in the destination
contains only the brief, the same workspace binding, and a pointer to the original.
Select it in Code to continue without initially resending the full old transcript.
Summaries are lossy and must be checked against files/history as needed.

Private handoffs and integrity receipts are saved in
~/.local/share/codexbar-claude-app/handoffs with private permissions. GitHub backup
uses the workspace's existing github.com origin, but only after reviewing/editing
the public draft and explicitly publishing it. The publisher creates a separate
branch and draft PR; it does not stage local changes or modify main. Emergency
transcript excerpts stay private instead of prepopulating the public draft.
Offline generation/publication does not remove the local brief.

Open the review from the Switch success dialog or run:

```sh
python3 ~/.local/lib/codexbar-cli/codexbar-claude.py handoff-review
```

Implementation: codexbar_claude_handoff.py. Qualified CLI2.1.299; flags verified
against its local help and [official CLI reference](https://code.claude.com/docs/en/cli-reference).
Tool-free live synthetic summarization and handoff-only resume passed; native
review-click behavior and GitHub request contracts are covered by isolated tests.
Owner account switching with the handoff extension and an actual reviewed GitHub
publication remain separate live checks. Preserved thinking stays organization-bound;
this feature transfers ordinary text, not reusable thinking state.
