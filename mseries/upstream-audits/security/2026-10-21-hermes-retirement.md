# Hermes retirement and Pillow advisory audit — 2026-10-21

The owner confirmed that Hermes is no longer used and authorized removing its
dependency lock despite the lock's exact Pillow pin. The maintained assistant
installer no longer clones or installs Hermes, and its configurator no longer
accepts a Hermes launcher, creates a Hermes profile, or writes a Hermes desktop
entry. The unused `mseries/local-ai/hermes-requirements.lock` was deleted.
Newelle and Crush setup is unchanged. This source change does not delete an
existing user's Hermes checkout, virtual environment, configuration, state, or
previously generated desktop launcher.

The removed lock pinned Pillow 12.3.0. Pillow's maintainers identify that
version as affected by GHSA-8g5g-8vmr-9782 / CVE-2026-112403 and list 13.0.0 as
the patched release. The Pillow project advisory rates it High; the GitHub
Advisory Database summary labels it Critical. The affected optional Hermes
environment was not the active everyday assistant path, which uses the managed
MLX model worker. Inspected image call sites did not establish a demonstrated
exploit path, and this audit found no evidence of compromise. The prior attempt
to bump Pillow in place could not resolve because Browser Harness 0.1.13
requires `pillow==12.3.0`; retiring the unused Hermes dependency set removes
that conflict without changing Browser Harness.

## Validation

- `bash -n mseries/local-ai/install-assistants.sh`
- `python3 -m py_compile mseries/local-ai/configure-assistants.py`
- `python3 -m unittest discover -s mseries/local-ai -p 'test_*.py'` — 72 passed
- `git diff --check`
- Follow-up CI found factory payload scripts rejected an empty `local-ai/*.lock` glob after the last lock was removed. `mseries/enhance.sh` now skips unmatched optional file patterns; the installer setup, image-wiring, and display-space regressions all pass locally (6 + 6 + 15 tests).

This receipt records source-level retirement only. No user-home environment or launcher was
modified, and no deployment or hardware qualification was performed.

Sources: [Pillow maintainer advisory](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782), [GitHub Advisory Database](https://github.com/advisories/GHSA-8g5g-8vmr-9782), [Browser Harness 0.1.13](https://pypi.org/project/browser-harness/0.1.13/).
