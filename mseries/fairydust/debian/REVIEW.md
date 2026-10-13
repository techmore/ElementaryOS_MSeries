# Review — build.sh / monitor.py / check-kernel-config.py / test-kernel-config.py

Scope: build correctness, CPU parallelism, process handling, isolation.
Experimental build-only port. Not a hardware-ready release. Do not distribute packages from this flow without the Must-fix items.

## Must fix before distributing packages

- `build.sh`: no `trap` for INT/TERM/EXIT. Build runs under `setsid` (new session), so Ctrl-C / caller exit orphans the kernel build and the disk watcher. Add trap killing `-$build_pid` and `$watch_pid`.
- `build.sh` disk watcher sends only `TERM`, no `KILL` fallback, no build-log retention. Add TERM → grace period → `KILL`, and tee full build output to `$work/build.log`.
- `build.sh` workdir isolation is exact-match only (`$here`, `$kit`, `/`). `$here/subdir` or any repo subtree passes. Canonicalize and reject `work` equal to or under repo/`kit`, and document allowed private dir.
- CPU parallelism oversubscription: default `jobs=$(nproc)` plus `DPKG_FLAGS="-j$jobs"` runs make-level and dpkg-level parallelism concurrently; can OOM / stall desktop on small ARM64 boxes. Cap default (e.g. `nproc-1`, memory-based limit) and document `FAIRYDUST_JOBS`. Verify `DPKG_FLAGS` vs `DEB_BUILD_OPTIONS=parallel=` for this tree.
- No signing / provenance / package QA: output is only `find *.deb + sha256sum`. Require GPG signing or checksum manifest, `lintian`/contents/maintainer-script+hook review before any distribution. Script warning at line 84 is not a gate.
- `monitor.py`: unbounded `while True`, `check=True` crash on `systemctl` error, `props['ActiveState']` KeyError, `int(ExecMainStatus)` ValueError. Add timeout/max-elapsed, try/except around `systemctl`, `.get()` defaults, safe int parse.
- `test-kernel-config.py::test_preserved_running_kernel_meets_strict_gate` requires `fairydust/usb4/running-config` host file. Fails with `FileNotFoundError` on clean checkout. Use checked-in fixture or `skipUnless(path.exists())`.
- Duplicated source identity: magic `ce9f2eba...` in `build.sh:38,40` and hardcoded `sourceCommit` in `monitor.py:25`. Single source of truth (env file / constant import).

## Should fix

- `build.sh:40`: `$(cat prepared-source.txt)` with `set -e` gives cryptic failure if missing/corrupt. Explicit existence check + message.
- `build.sh:48`: config-gate failure (`exit 1` on missing symbols) is hidden — stdout goes to `kernel-config-report.json`, reason not echoed. `cat` report on failure.
- `build.sh:30,42`: `--compile` path does not validate `$out`/`.config` exist before `cd/make`.
- `monitor.py`: validate `unit` (e.g. must end `.service`, no path) and constrain `status` output path; currently any writable path can be overwritten. `fsync` before `replace` for crash safety.
- `check-kernel-config.py`: last-wins on duplicate symbols is implicit; fine for `.config` but document. `decode()` encoding is implicit UTF-8; already catches `UnicodeError`.
- `test-kernel-config.py`: only `inspect()` is tested, not `main()` exit codes (0/1/2). Add one CLI-level test.

## Correct / keep

- Non-root, native `aarch64`, required env vars, free-space pre-checks, `sha256sum -c` pinning of archive/config/patch, `patch --batch --fuzz=0`, `olddefconfig` + `check-kernel-config.py --require fairydust` gate, `rustavailable`, reproducible `KBUILD_BUILD_*`, atomic status write via `.tmp`+`replace`, `n` vs `absent` distinction and `ARM64_16K_PAGES=y` strictness with tests.

## Maintainer disposition

Applied: process-group cleanup traps and TERM/KILL fallback, retained build
log, reject repository-subtree workdirs, explicit prepared-input checks,
echo failed config report, CLI exit-code regression. Current compilation
runs in a systemd user cgroup, whose stop action covers all children.

The CPU claim is not supported by this tree: bindeb-pkg delegates to one
Debian build-arch target; outer make and dpkg job counts do not multiply
independent kernel builds. Explicit DPKG_FLAGS overrides upstream's -j1;
all ten jobs are intentional at the owner's request. Memory/space must be
observed and FAIRYDUST_JOBS can reduce concurrency.

running-config is checked into Git, not an untracked host dependency, so
that regression fixture works in a clean checkout. Checksums are already
generated; package contents, hooks, source/license publication and image
qualification remain required before distribution. No release is being
published by this script. Monitor hardening remains follow-up; the live
monitor is a scoped local user service, not an external-input endpoint.


Build follow-up: first packaging exposed the concurrent DTB `install -D`
parent-directory race. Patch 0002 precreates the Apple DTB directory; the
successful .3 package staged every DTB. Runtime dependency patch is included.
The package hooks still require mkosi-specific adaptation and remain untested.
