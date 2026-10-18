# Working agreement for Codex, Claude Code, and OpenCode

> **PRIMARY GOAL:** a picture on the WD22TB4 dock's HDMI from elementary OS on this j314s.
> Current J314S host: owner confirms the dock works on Aurora .20; external 1080p/60 is active.
> [Scoped VRR/dock result](mseries/aurora/hardware-tests/2026-10-18-j314s-vrr-and-boot-archive.md)
> records a visual pass and brief kernel VRR activation. Sustained VRR, long-run dock stability,
> physical-port verification and suspend/resume remain open. Check this result before repeating older RE.
> Gates, prior art and rules: [mseries/fairydust/usb4/PRIMARY-GOAL.md](mseries/fairydust/usb4/PRIMARY-GOAL.md).

> **CODEXBAR IS A CUSTOM PORT, NOT STOCK UPSTREAM.** We run upstream
> [steipete/CodexBar](https://github.com/steipete/CodexBar) (Linux ARM64 CLI + Qt desktop, pinned in
> `mseries/install-codexbar.sh`) and add our own elementary OS layer on top: the Wingpanel indicator
> (`mseries/codexbar-wingpanel/`), the wrapper, the sessions and OpenCode-local helpers, and Codex/Claude
> account switching (upstream's managed Codex accounts are macOS-only). The full list of our mods and the
> repeatable upgrade checklist is `mseries/CODEXBAR-PORT.md`; verify with `bash mseries/check-codexbar-port.sh`.
> When you bump upstream, **merge it
> with our customizations**: never replace our files with the stock ones, re-check that the panel still reads
> `codexbar-linux --snapshot` (schema), and keep the port current with each upstream release. After every push
> that touches CodexBar, run `bash mseries/deploy-codexbar.sh`. Routine deploys must leave Wingpanel and the
> CodexBar daemon running; native-module changes load at next login. Use `--restart` only for an owner-requested
> reload or recovery from a confirmed panel defect, and state when code is installed but not yet loaded. Record the pin,
> what you re-verified and what is still unverified in `mseries/OS9-HANDOFF.md`.

- Keep `mseries/OS9-HANDOFF.md`, `mseries/ROADMAP.md`, and relevant public
  status pages current as work lands. Record concrete changes, commands,
  verification results, blockers, and the next task.
- Keep the owner’s menu bar stable: stage routine indicator updates without restarting Wingpanel. Reload only when the owner explicitly requests it or to recover from a confirmed panel defect.
- Commit and push completed, reviewed batches to GitHub. Use one agent for
  Git writes at a time. A delegated worker must report to its coordinator
  instead of committing unless explicitly assigned ownership of Git writes.
- Codex/Claude handle implementation and review; OpenCode can handle build
  checks and log analysis. Read the latest handoff before starting work.
- Before speech, dictation or voice work, read the [canonical qualification ledger](mseries/dictation/QUALIFICATION-INDEX.md)
  and its [JSON index](mseries/dictation/qualification-index.json). Reuse completed
  passes and failures; never repeat a comparable finished trial or duplicate an
  owned queue. Inspect the units/lock and resume only incomplete cases with the
  same recorded identity. Preserve prior receipts and update the ledger after a
  concrete fix or deployment. For MCP/app workflows, first read
  [the app integration record](mseries/local-ai/APP-INTEGRATION.md) and its retained
  receipts; completed adapter/model cases are evidence to reuse too.
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
