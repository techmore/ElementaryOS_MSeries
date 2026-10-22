# Keeping the dev machine clean

The weekly cleanup lives in this repository: [`dev-clean/dev-clean.sh`](dev-clean/dev-clean.sh),
installed for the user by [`dev-clean/install.sh`](dev-clean/install.sh) as `~/.local/bin/dev-clean`
(`~/bin/dev-clean` becomes a link to it, so the old habit keeps working) with the
`dev-clean.timer` user timer (`OnCalendar=weekly`, persistent, up to an hour of random delay, run at
idle I/O priority; the log of the last run is `~/.cache/dev-clean/last.log`). `dev-clean --dry-run`
prints what would go and removes nothing; `install.sh --uninstall` removes the timer and the script.
The owner runs `bash mseries/dev-clean/install.sh` once; an agent does not enable timers.

## What one run removes

| What | Rule | Why it is safe |
|---|---|---|
| `rust/target` inside any checkout under `~/Projects`, `~/claude-work`, `~/src`, `~/ElementaryOS_MSeries*` | always | `~/.cargo/config.toml` builds everything in `~/.cache/cargo-target`; a stray target is an override gone wrong |
| `~/.cache/cargo-target` | no build for 7 days | cargo rebuilds the dependencies once |
| `node_modules` under `~/src`, `~/claude-work` | always | regenerable |
| Build caches in `~/.cache` (mseries-build, playwright, tracker3, electron, pip, mesa shader cache, mlx candidates, venvs) | always | regenerable |
| Claude session scratch `/tmp/claude-1000/*/<session>` | older than 2 days | `/tmp` is RAM; sessions keep nothing durable there |
| `~/Documents/Codex/<dated folder>` (`2026-10-21`, `name-20261021`) | older than 3 days | goes to the **Trash** with `gio trash`, not deleted; undated folders are kept |
| podman unused images, containers, volumes | always | images come back from their Containerfile |
| git worktree records whose directories are gone | every main checkout under `~/Projects` and `~/ElementaryOS_MSeries` | `git worktree prune` only drops bookkeeping; retiring merged worktrees stays manual ([REPO-HYGIENE.md](REPO-HYGIENE.md)) |
| journal over 100 MB, apt cache (when sudo needs no password), unused flatpak runtimes | always | regenerable |

Nothing under `~/Documents` other than the dated Codex exports, nothing under `~/vms`, and no
repository content is touched.


## What happened today

The UI stuttered with no fan ramp. CPU was fine. The machine was out of memory and out of disk:

| Resource | State at 19:21 |
|---|---|
| Root disk (203 GB btrfs) | 100% used, 1.7 GB free |
| RAM (30 GB) | 178 MB free, 8 GB zram swap completely full |
| /tmp (tmpfs, lives in RAM) | 6.4 GB, mostly Claude session scratch + a 2.6 GB llama model |
| Load average | 17 five minutes earlier, 6 at the time |

When swap is full and the disk is full, the kernel evicts file pages constantly and every click waits on I/O. That is a stutter with a cool CPU.

Where the disk went:

| Thing | Size | Regenerable? |
|---|---|---|
| Rust `target/` dirs, one per worktree (22 found) | ~55 GB | yes, `cargo build` |
| `rust/target/` **tracked in git on origin/main** of ElementaryOS_MSeries (377 files, 35 MB), not in `.gitignore` | fixed in PR #458 | yes, fix once |
| `~/.cache` build caches (mseries-build, playwright, tracker3, mlx candidates) | ~10 GB | yes |
| `src/opencode-v2/node_modules`, qemu build | 3.6 GB | yes |
| podman unused images/volumes | 1.4 GB | yes |
| Documents 75 GB, vms 50 GB | 125 GB | **no, yours, untouched** |

## Done today

- Deleted the Rust targets, caches, node_modules, podman leftovers. Freed about 40 GB in total.
- Added a 16 GB disk swap file at `/swap/swapfile` (btrfs subvolume, in fstab, priority 10 so the 8 GB zram still fills first). Swap total is now 24 GB. Net after the swap file: 16 GB free (93% used).
- `~/.cargo/config.toml` now points every repo and worktree at one shared `~/.cache/cargo-target`. Dependencies compile once instead of once per worktree.
- `dev-clean` script, now `mseries/dev-clean/dev-clean.sh` in this repository with a weekly user timer (`mseries/dev-clean/install.sh`); `~/bin/dev-clean` becomes a link to the installed copy.

## Rules going forward

1. **One build dir.** Never delete `~/.cargo/config.toml`. If a worktree still grows a `rust/target`, something overrode `target-dir`; fix the override.
2. **Repo fixed.** `rust/target` is untracked and ignored on main as of PR #458 (2026-10-21).
3. **Worktrees are temporary.** 40 in `~/Projects/ElementaryOS_MSeries`, 61 in `~/ElementaryOS_MSeries`, 18 in rupert. Retire a worktree the day its PR merges. `dev-clean` prunes stale ones; retiring merged ones is a manual pass, see `mseries/REPO-HYGIENE.md` for the method.
4. **/tmp is RAM.** Nothing bigger than a few MB belongs there: no models, no repo clones. Put models under `~/.local/share/mseries-ai/models`, clones under `~/claude-work`. To stop Claude sessions filling RAM, move the scratch root to disk once no session is running:
   ```bash
   mv /tmp/claude-1000 /var/tmp/claude-1000 && ln -s /var/tmp/claude-1000 /tmp/claude-1000
   ```
5. **Session discipline.** 15 `claude` processes and 20 `claude-desktop` processes were alive, plus ChatGPT, Codex and Brave: ~10 GB just in agents and browsers. Keep roughly five sessions live, archive the rest. Every session that starts a dev server stops it before it ends.
6. **Weekly:** the `dev-clean.timer` user timer runs `dev-clean` (log in `~/.cache/dev-clean/last.log`); `dev-clean --dry-run` previews. Monthly: look at `du -xsh ~/* | sort -rh` for anything new.

## Containers: podman → incus

Yes, move development containers to incus. Reasons, honestly weighed:

- **Performance:** both are kernel namespaces on the host, so CPU is identical. Incus on the btrfs storage pool skips the overlay filesystem layer podman uses, so disk I/O (Rails boot, asset builds, tests) is somewhat faster, and clones are copy-on-write snapshots that take seconds and almost no space.
- **Visibility:** Orchard already has an Incus front end (`mseries/orchard-incus`, branch `claude/orchard-incus`). Everything in incus shows up there. The podman panel in the `mseries-orchard-podman` worktree becomes unnecessary; park it.
- **Memory:** podman was not the memory problem (12 Rupert containers used under 1 GB together). The gain is fewer duplicate images (32 images, 3.3 GB) and one place to see and kill things.
- **What podman does better:** reproducible images from a Containerfile. Keep podman only for third-party images that ship that way (the anisette server).

How to run Rupert in incus:

```bash
# one base container with Ruby, Postgres client, node; snapshot it
incus launch images:debian/13 rupert-base
# ...install deps once, then
incus snapshot create rupert-base clean

# per worktree: clone the snapshot, bind-mount the worktree, expose the port
incus copy rupert-base/clean rupert-cashflow
incus config device add rupert-cashflow src disk source=$HOME/Projects/rupert-cashflow path=/srv/rupert
incus config device add rupert-cashflow web proxy listen=tcp:127.0.0.1:3588 connect=tcp:0.0.0.0:3000
incus start rupert-cashflow
incus exec rupert-cashflow -- sh -c 'cd /srv/rupert && bin/rails s -b 0.0.0.0'
```

When the PR merges: `incus delete -f rupert-cashflow`. Orchard shows it the whole time.

Existing incus containers: `deb-test`, `orchard-test`, `rupert-dev` (idle, nothing running in it). Start the migration by building the `rupert-base` snapshot from what `rupert-dev` already has.

## Still open

- 2.9 GB of repo clones sit in RAM at `/tmp/claude-1000/-home-sdolbec-Projects/b453e662-…/scratchpad` from a session idle since 18:31. Delete when that session is done.
- The bakeoff llama model (2.6 GB) is also in `/tmp`. Move to disk when the bakeoff ends.
- zram is capped at 8 GB with `vm.swappiness=100`. With the disk swap in place that is fine; raising the cap to 12 GB would trade ~2 GB RAM for less disk swapping.
