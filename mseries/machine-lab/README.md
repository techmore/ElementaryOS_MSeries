# Machine Lab has moved

Machine Lab is now the **Machines** section of [Orchard](../orchard/README.md)
(`mseries/orchard/`), merged on 2026-10-21 with Orchard for Incus into one app that keeps
Machine Lab's sidebar, pages and style and uses Orchard's name and icon.

- Sources: `mseries/orchard/src/` (`machine.vala`, `page.vala`, `viewer.vala`, `display.vala`,
  `clipsync.vala`, `snapshots.vala`, `images.vala`, `unattend.vala`, `virtiowin.vala`,
  `windows-ui.vala`, `macexp.vala`), launcher helpers in `mseries/orchard/launcher/`.
- Install: `bash mseries/install-orchard.sh` (replaces `install-machine-lab.sh`).
- Guides: `mseries/orchard/docs/USER-GUIDE.md`, `mseries/orchard/ROADMAP.md`,
  `mseries/orchard/CHANGELOG.md`.

Your machines are untouched: `~/.config/machine-lab/machines.ini`, `~/.local/share/machine-lab/`
and `~/vms/*/vm.conf` are read by Orchard as before. History: `git log --follow mseries/orchard/src/page.vala`.
