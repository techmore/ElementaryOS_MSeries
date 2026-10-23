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
