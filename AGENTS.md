# Working agreement for Codex, Claude Code, and OpenCode

- Keep `mseries/OS9-HANDOFF.md`, `mseries/ROADMAP.md`, and relevant public
  status pages current as work lands. Record concrete changes, commands,
  verification results, blockers, and the next task.
- Commit and push completed, reviewed batches to GitHub. Use one agent for
  Git writes at a time. A delegated worker must report to its coordinator
  instead of committing unless explicitly assigned ownership of Git writes.
- Codex/Claude handle implementation and review; OpenCode can handle build
  checks and log analysis. Read the latest handoff before starting work.
- The owner explicitly approved OpenCode's configured provider receiving
  repository build configuration/handoffs and public GitHub Actions build
  logs (including environment/package details) for scoped build analysis.
- Record public source revisions and retain licenses/attribution. Do not
  import sponsor-only content without confirming redistribution permission.
- Distinguish the working transformed desktop from the unbuilt/unqualified
  factory image. The first factory ISO now builds, but hardware boot remains
  unverified. Never describe configuration checks or image assembly as a
  successful boot.
- Do not change the owner's bootloader, kernel, or running audio stack as
  part of image work. Preserve unrelated local changes and untracked drafts.
- Maintain the Omarchy Mac package boundary described in `mseries/PORT-MAP.md`.
