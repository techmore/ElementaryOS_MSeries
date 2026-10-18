# GitHub repository dashboard in elementary OS

`steipete/RepoBar` is a native macOS menu-bar app, so its application bundle
does not run on elementary OS. This optional port provides the core repository
overview as a native Pantheon Wingpanel indicator instead. It is an independent
implementation; no macOS source or binary is copied into this project.

## Ported features

- Searchable dashboard with dashboard, all, pinned, issues, pull requests, and
  needs-attention views. The dashboard defaults to five recently updated
  repositories; pins stay visible. Forks and archived repositories are hidden
  by default outside the all-repositories view.
- Repository cards show open issue/PR counts, default-branch CI, stars, branch,
  latest release, recent issue/PR/commit activity, and local branch health when
  a projects folder is configured. Repository and activity links open in the
  browser.
- Pin, unpin, hide, and show preferences are available from Wingpanel and CLI.
- CLI details cover issues, pulls, CI runs, releases, activity, commits,
  branches, tags, and commit activity. Additional commands report API quotas,
  authentication, cache status, and preferences.
- Uses GitHub CLI authentication and GraphQL/REST requests; the helper never
  reads, stores, or prints the token. Cache and settings use private
  permissions (`0700` directories, `0600` files) because they can contain
  private repository names.
- Optional local scanning skips hidden folders and symlinks and is bounded by
  depth and directory count. `local sync` is explicit: it refuses dirty or
  detached checkouts and only fast-forwards a clean branch after fetching.
- Refresh interval, repository limit, menu sort, host, fork/archive visibility,
  and local scan root/depth are configurable with the CLI.

This port implements the repository dashboard and CLI surfaces, not every
macOS-only interaction. Visitor/cloner traffic, the contribution heatmap UI,
multi-account UI, a launch-at-login preference pane, and full repository
submenus are not yet represented in Wingpanel. The CLI exposes a raw
commit-activity endpoint. Upstream changes are never merged automatically;
preserve this project's Pantheon UI and Linux integration.

## Install on elementary OS

Run `bash mseries/install-repobar-wingpanel.sh`. Then connect GitHub with
`gh auth login` (or `mseries-repobar auth login`), reopen Wingpanel, and use the
`GH` panel item. The installer is optional and is not included in the base
image. `gh` controls authentication; the port does not handle the token.

Useful commands after installation:

```sh
mseries-repobar repos --scope all --search linux
mseries-repobar issues owner/repository
mseries-repobar rate-limits
mseries-repobar settings set local-root ~/Projects
mseries-repobar local scan
mseries-repobar local sync ~/Projects/repository --yes
```

Local sync changes a checkout only after explicit `--yes` confirmation, and
only when it is clean and can fast-forward.

Remove the indicator and helper with
`bash mseries/install-repobar-wingpanel.sh --uninstall`. This leaves the cached
snapshot in `~/.cache/mseries/repobar/` so the user can remove it separately.

## Source

- Reference project: [steipete/RepoBar](https://github.com/steipete/RepoBar)
- Linux implementation: `repobar.py` and `repobar-wingpanel/`
- Installer: `install-repobar-wingpanel.sh`
