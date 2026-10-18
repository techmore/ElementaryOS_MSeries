# GitHub repository dashboard in elementary OS

`steipete/RepoBar` is a native macOS menu-bar app, so its application bundle
does not run on elementary OS. This optional port provides the core repository
overview as a native Pantheon Wingpanel indicator instead. It is an independent
implementation; no macOS source or binary is copied into this project.

## Ported features

- Searchable dashboard with dashboard, all, pinned, issues, pull requests, and
  needs-attention views. The dashboard defaults to 20 recently updated
  repositories; pins stay visible. Forks and archived repositories are hidden
  by default outside the all-repositories view.
- Repository cards show open issue/PR counts, default-branch CI, stars, branch,
  latest release, recent issue/PR/commit activity, and local branch health when
  a projects folder is configured. Repository and activity links open in the
  browser.
- Each repository card includes default-branch commit counts for rolling 1-hour,
  24-hour, and 30-day windows. Counts are returned with the paginated repository
  snapshot and share its five-minute cache.
- The panel badge is the GitHub mark rendered as a GTK symbolic icon, so it
  follows the current theme's foreground color.
- The Wingpanel menu shares CodexBar's compact elementary OS styling: 9 pt body
  text, 8 pt captions, softly raised cards, consistent popover spacing, and a
  rounded refresh dock. Search, scope selection, and repository-specific details
  keep their own useful width and hierarchy.
- A globe beside the repository name opens its GitHub Pages site (custom
  domains included), or the repository's website when it has no Pages site.
- A For You card leads the dashboard with pull requests waiting on your review
  and issues assigned to you. Optional desktop notifications announce a default
  branch that starts failing CI or passes again (RepoBar Settings → Notifications).
- Each repository card has a compact GTK disclosure menu for issues, pull
  requests, workflow runs, releases, activity, commits, branches, and tags.
  Categories fetch their data only when expanded; links open the matching GitHub
  item. Search also matches repository topics, and the Local view filters to
  checkouts found by the configured local scan.
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
multi-account UI, and a launch-at-login preference pane are not yet represented
in Wingpanel. The CLI exposes a raw commit-activity endpoint. Upstream changes
are never merged automatically; preserve this project's Pantheon UI and Linux
integration.

## Look and feel

The popover follows the CodexBar indicator's elementary OS styling: a segmented
scope switcher (Dashboard, Pinned, Attention, All), cards led by a CI status dot
with PR and issue pills, a star to pin, a chevron for details, a right-click menu
for open / copy link / pin / hide, and the same bottom bar (status chip,
freshness, icon dock). Render it headlessly with
`repobar-wingpanel/probe/run-probe.sh BUILD_DIR OUT_DIR [light|dark]` after
`meson setup BUILD_DIR mseries/repobar-wingpanel && ninja -C BUILD_DIR`.
The dock's gear opens **RepoBar Settings** (`mseries-repobar-settings`), a
native window whose switches apply immediately. Keyboard: type to search,
arrow keys and Enter on cards, Ctrl+F, Ctrl+R, Alt+1…4 for the tabs.
`bash mseries/deploy-repobar.sh` rebuilds and installs the module and helper
without apt; add `--restart` to reload Wingpanel.

## Install on elementary OS

Run `bash mseries/install-repobar-wingpanel.sh`. Then connect GitHub with
`gh auth login` (or `mseries-repobar auth login`), reopen Wingpanel, and use the
GitHub icon in the panel. The installer is optional and is not included in the
base image. `gh` controls authentication; the port does not handle the token.

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
- Wingpanel icon: GitHub mark path from [Simple Icons](https://github.com/simple-icons/simple-icons), whose GitHub entry points to [GitHub's logo assets](https://github.com/logos). The SVG is tintable for GTK's current theme; the mark remains GitHub's trademark.
- Installer: `install-repobar-wingpanel.sh`
