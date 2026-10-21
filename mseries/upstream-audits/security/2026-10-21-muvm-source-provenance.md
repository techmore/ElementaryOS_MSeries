# Optional muvm source provenance — 2026-10-21

Baseline: dev `03d9ced4f0b161af1460ac951b4b8bdd49a3a524`.
The existing installer skipped cloning whenever its cache directory existed,
without checking origin, revision or edits, then built and installed that tree.
This confirms an identity/reproducibility gap, not a demonstrated compromise or
a privilege escalation: the owner already chooses the installer/build workspace.

## Exact retained versions

| Source | Version | Commit (GitHub tag API resolves directly to commit) |
|---|---|---|
| [AsahiLinux/muvm](https://github.com/AsahiLinux/muvm/tree/b761e07b84652e7fb00df83315907c1809899080) | muvm-0.7.0 | b761e07b84652e7fb00df83315907c1809899080 |
| [libkrun](https://github.com/libkrun/libkrun/tree/227b2de6ed323fe180e02f871c5f325a90c13cc2) | v1.19.6 | 227b2de6ed323fe180e02f871c5f325a90c13cc2 |
| [libkrunfw](https://github.com/libkrun/libkrunfw/tree/f14ac64ca8a04c6c9d76cac1c61ee050809c88c9) | v5.6.2 | f14ac64ca8a04c6c9d76cac1c61ee050809c88c9 |

Upstream containers/libkrun and containers/libkrunfw URLs redirect to the libkrun
organization. The installer retains its existing origin URLs, so valid existing
clones remain compatible. No upstream code, version or license was imported.

The helper validates standalone, nonsymlink caches against the exact configured
origin and HEAD, rejects tracked edits and untracked source files, and preserves
ignored build outputs. It never resets an owner's checkout. New clones stage in
a private sibling directory, verify the tag's immutable commit before checkout,
and refuse an intervening destination. Download/validation precedes privileged
APT/source installation. Tag movement fails closed.

## Checks and recovery

`python3 mseries/test-muvm-source.py`: 11 offline tests passed: new clone, reusable
clean cache, ignored output preservation, dirty tracked/untracked source refusal,
wrong origin/HEAD, moved tag, unrelated directory, symlink and malformed pin.
Installer ordering is checked as well. The same test is wired into `validate.sh`.
Bash syntax, warning-level ShellCheck and whitespace checks pass. No actual
source build, sudo, apt, FEX/VM launch, package installation or live desktop change.

Recovery for a refused cache: preserve/move the named tree, then rerun the normal
installer to acquire the exact recorded sources. Do not discard owner edits.
No installed artifact was changed, so this source patch needs no runtime rollback.
This is not signature validation, a full dependency audit, or hardware qualification;
FEX's signed APT source and rootfs acquisition remain separate trust boundaries.
