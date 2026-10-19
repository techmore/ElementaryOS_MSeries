# Branch model

Two long-lived branches:

| Branch | Role | Who merges into it |
| --- | --- | --- |
| `main` | **Stable.** For now `main` is the `v0.0.1` stable line: what the owner runs and what release builds are cut from. | Only release PRs from `dev`, plus urgent hotfixes. |
| `dev` | **Integration.** Every finished feature/fix branch lands here first. | Feature PRs (`claude/*`, `codex/*`, `deepseek/*`, …). |

## Day-to-day

1. Branch from `dev`: `git fetch origin && git worktree add -b claude/<topic> <dir> origin/dev`.
2. Open the PR with `--base dev` (`gh pr create --base dev`). CI runs on PRs to
   both `dev` and `main`.
3. Merge into `dev` when CI passes and the change is reviewed. Deploy steps that
   AGENTS.md requires (for example `mseries/deploy-codexbar.sh`) still apply.

## Promoting to stable

When `dev` has a batch that has been running on the owner's machine without
regressions, open a release PR `dev` → `main` titled `Release v0.0.N`, list what
changed and what was verified (and what was not), merge it with a merge commit,
then tag `main`: `git tag -a v0.0.N -m "v0.0.N" origin/main && git push origin v0.0.N`.

## Hotfixes

A fix that cannot wait for the next release branches from `main`, goes to `main`
by PR, and is then merged back into `dev` (`dev` must never be behind `main`).

## Later: maintenance branches

While there is only one stable line, `main` is it. Once `v0.0.2` work starts and
`v0.0.1` still needs fixes, cut `v0.0.1-stable` from the `v0.0.1` tag and send
`v0.0.1` hotfixes there instead.

## PRs opened before this model

Open PRs that already target `main` may be merged there; afterwards merge `main`
back into `dev`. New PRs target `dev`.
