# PR workflow cancellation

Every workflow triggered by `pull_request` uses a workflow-scoped, PR-scoped
concurrency group. New revisions cancel the whole older run, including queued
jobs and its matrix. Different workflows and PRs do not cancel each other.
Cancellation is conditional on the PR event: manual and publishing runs keep
serialization without being interrupted. The package publisher's separate
cross-branch lock remains unchanged.

Run the same checks as CI:

```sh
python3 -m pip install -r mseries/ci/requirements.txt
python3 mseries/ci/workflow_policy.py
python3 -B -m unittest discover -s mseries/ci -p 'test_*.py' -v
```

The policy checks every PR workflow, so adding a new workflow without cancellation
fails. It also requires unique workflow names because the name is part of the
concurrency group. Regression tests deliberately remove or misconfigure policies
and check group isolation and preservation of publisher/release serialization.

This takes effect for runs using the updated workflow revision. It does not
cancel existing legacy runs retroactively or reserve runner capacity for Rupert;
current builds still share the GitHub account's runner capacity. GitHub's
[concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
describes the cancellation semantics used here.

For a live cancellation check, record the current PR run IDs, then push a newer
commit to the same PR. Confirm the older active runs finish as `cancelled` and
replacement runs refer to the new head. Record another PR's run before and after
to check isolation. A manual package run on the test branch with `publish=false`
can serve as the non-PR control: a PR push must not cancel it. Never enable
publishing just to test cancellation. The regression suite separately checks
that the publishing job excludes PR events and retains its non-cancelling global
lock. Stop an unfinished synthetic manual control after recording the result.

## Aurora dependency downloads

`install_aurora_tools.py` runs only as root on an ephemeral Ubuntu ARM64 GitHub
runner. It uses a temporary signed Ubuntu source configuration, trying the
official HTTPS ports archive before HTTPS Azure. Existing runner sources and
third-party repositories are untouched. Each mirror gets 60 seconds for metadata
and 240 seconds for a download-only install, with connection timeouts and limited
retries. Failure switches mirrors before dpkg begins. Once verified archives are
ready, installation runs with `--no-download`. Both mirror failures stop CI.
Normal Ubuntu archive signature verification remains enabled. Rustup and the
overall workflow dependency step have separate time limits.


## Rust candidate dependency downloads

`install_rust_tools.py` selects the Rust-lane build/test packages using the same
bounded signed download engine. Aurora's default package profile is preserved.
The Rust profile includes explicit Clippy, debootstrap, gpgv and system Python
YAML support and installs without recommendations. The workflow tests the shared
installer, watches changes under `mseries/ci/`, and bounds the dependency step.
Ten installer regressions plus nine workflow-policy checks pass locally; the
new Rust profile still requires Linux CI qualification. This is CI bootstrap
and oracle provisioning, not production native OS acquisition.
