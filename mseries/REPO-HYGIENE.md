# Repository hygiene: branches, worktrees, PRs (audit, 2026-10-16)

Read-only audit by Claude against `origin/main` (`299e415`). **Nothing was deleted,
merged or moved.** Deletions are the owner's decision. "Ahead" counts are commits
not reachable from main; "patch-unmerged" uses `git cherry`, which cannot see
squash merges, so a nonzero number on a branch whose PR is merged means "verify",
not "unmerged work".

## Branches

| Branch | vs main (behind/ahead) | Owner / purpose | Suggested action |
|---|---|---|---|
| `main` (local) | 43 / 0 | stale local copy | fast-forward to `origin/main` |
| `feat/power-gpu-finding` | 0 / 0 | checked out in `wt-darkmode` | fully merged; delete after the worktree is retired |
| `feat/power-opportunities` | 2 / 0 | power survey | fully merged; delete |
| `feat/universal-dark-mode` | 4 / 0 | dark mode | fully merged; delete |
| `network-saturation` | 4 / 1 (0 patch-unmerged) | PR #54 merged | delete; `ElementaryOS_MSeries-main` worktree sits on it |
| `brightness-sub-floor` | 0 / 1 | brightness work, `wt-brightness` | open a PR (one commit on main's tip) |
| `codex/guide-collapsed-by-default` | 8 / 3 | CodexBar sessions panel; checked out in the shared checkout with uncommitted work from several agents | owner/Codex: PR it; do not clean the checkout blindly |
| `docs/dock-video-decision` (PR #53, open) | 31 / 63 | dock video RE, DeepSeek/Codex/Claude | mergeable now (`git merge-tree` clean); merge once the reboot work settles |
| `claude/dock-video-review` | 31 / 63 | same commits as the branch above (fast-forwarded) | delete after PR #53 merges |
| `re/usb4-exp2` | 31 / 19 | original experiment-2 implementation; same patch as the docs branch (`DP-TUNNEL-RE.md` says syncing is no longer needed) | keep until PR #53 merges, then archive/delete |
| `backup-docs-pre-merge` | 31 / 21 | backup before a docs merge | verify its content is in PR #53, then delete |
| `feat/window-snapping` | 67 / 16 (PR #48 merged) | window snapping | likely squash-merged; verify then delete |
| `deb/mseries-plugin-repo` | 35 / 5 | .deb plugin repo (issue #52) | owner: PR or park |
| `rust/mseries-power-port` | 43 / 2 | Rust port of mseries-power | owner: PR or park; far behind main |
| `origin/claude/orchard-incus` | 8 / 11 | Orchard for Incus | owner: PR or park |

## Worktrees

| Path | Branch | Note |
|---|---|---|
| `~/ElementaryOS_MSeries` | `codex/guide-collapsed-by-default` | the shared checkout. Many uncommitted changes and untracked drafts from several agents (brightness, network, kernel-install scripts, `rust/`, `orchard-incus/`). Several untracked usb4 docs are older copies of files on the dock branch: do not trust them, read the branch. |
| `~/ElementaryOS_MSeries-main` | `network-saturation` | branch is merged; point it at `main` or remove |
| `~/wt-brightness` | `brightness-sub-floor` | active |
| `~/wt-darkmode` | `feat/power-gpu-finding` | branch fully merged; likely retirable |
| `~/wt-dockvideo` | `docs/dock-video-decision` | Codex/DeepSeek; has uncommitted edits to `OS9-HANDOFF.md` and `STATE-OF-PLAY.md` and is behind the remote, so expect a small merge there |
| `~/wt-claude-dockvideo` | `claude/dock-video-review` | Claude; retire after PR #53 merges |

## Pull requests

- Open: #53 (dock DP tunnelling, mergeable, 56 files).
- #54 merged (network saturation), #48 merged (window snapping and kernel images).

## Conventions this audit supports (from AGENTS.md and memory)

- One Git writer at a time per branch; push to a shared branch only after
  `git fetch` shows it has not moved; never `git add -A` in the shared checkout.
- Hardware facts live in each effort's ledger (dock video: `fairydust/usb4/STATE-OF-PLAY.md`);
  `OS9-HANDOFF.md` gets one short entry per batch, not a copy of the ledger.
- Kernel feature set belongs to DeepSeek; Claude proposes via docs and PR comments.

## Proposed cleanup, in order (each needs the owner's yes)

1. Merge PR #53 when the reboot batch is recorded, then delete `claude/dock-video-review`,
   `backup-docs-pre-merge` (after content check) and archive `re/usb4-exp2`.
2. Delete the three fully merged local branches and `network-saturation`; update the
   two worktrees that sit on them.
3. Open PRs for `brightness-sub-floor` and `codex/guide-collapsed-by-default`.
4. Decide `deb/mseries-plugin-repo`, `rust/mseries-power-port`, `orchard-incus`.
5. Add pointers to `ROADMAP.md`/`OS9-HANDOFF.md` on main for the dock ledger when #53 lands.
