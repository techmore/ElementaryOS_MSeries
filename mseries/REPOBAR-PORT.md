# GitHub repository status in elementary OS

`steipete/RepoBar` is a native macOS menu-bar app, so its application bundle
does not run on elementary OS. This optional port provides the core repository
overview as a native Pantheon Wingpanel indicator instead. It is an independent
implementation; no macOS source or binary is copied into this project.

## Current scope

- Lists repositories accessible to the active GitHub CLI account, including
  private repositories the account can read.
- Shows open issue and pull-request counts, default-branch CI state, stars,
  default branch, latest release tag, and archive state.
- Opens a repository in the browser when selected.
- Refreshes on demand and every five minutes. A local snapshot lets the panel
  render cached information while GitHub is unavailable.
- Makes read-only GitHub GraphQL requests through `gh`; the helper does not
  store or print the GitHub token. The cache is user-private (`0700` directory,
  `0600` file) because it can contain private repository names.

Local checkout health, activity feeds, pin/hide filters, release pages, and
issue/PR drill-down are not implemented yet. RepoBar upstream remains a watched
reference for future feature parity; upstream changes are never merged
automatically.

## Install on elementary OS

Run `bash mseries/install-repobar-wingpanel.sh`. Then connect GitHub with
`gh auth login`, reopen Wingpanel, and use the `GH` panel item. The installer is
optional and is not included in the base image.

Remove the indicator and helper with
`bash mseries/install-repobar-wingpanel.sh --uninstall`. This leaves the cached
snapshot in `~/.cache/mseries/repobar/` so the user can remove it separately.

## Source

- Reference project: [steipete/RepoBar](https://github.com/steipete/RepoBar)
- Linux implementation: `repobar.py` and `repobar-wingpanel/`
- Installer: `install-repobar-wingpanel.sh`
