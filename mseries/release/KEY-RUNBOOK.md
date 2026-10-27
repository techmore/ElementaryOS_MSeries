# Repository signing key: create, install, rotate

Owner decision (2026-10-21): a dedicated key, kept offline; only a **signing subkey** lives in the
`MSERIES_APT_KEY` Actions secret. Never reuse a personal key. This is done by the owner on an offline
or trusted machine; CI never creates keys. Until the secret exists the pipeline builds, tests and
publishes nothing (`mseries/RELEASE-PIPELINE.md`).

## Create (once)

```bash
export GNUPGHOME=$(mktemp -d); chmod 700 "$GNUPGHOME"
gpg --quick-gen-key 'M-series apt repository <sdolbec1@gmail.com>' ed25519 cert never
FPR=$(gpg --with-colons --list-keys | awk -F: '$1=="fpr"{print $10; exit}')
gpg --quick-add-key "$FPR" ed25519 sign 1y          # signing subkey, one-year expiry
# Back up the whole key (primary included) offline: encrypted USB or hardware token, two copies.
gpg --armor --export-secret-keys "$FPR" > mseries-primary-BACKUP.asc
# The CI secret holds the subkey only: --export-secret-subkeys leaves the primary secret out.
gpg --armor --export-secret-subkeys "$FPR" > mseries-ci-subkey.asc
gh secret set MSERIES_APT_KEY < mseries-ci-subkey.asc
# If the subkey has a passphrase, also: gh secret set MSERIES_APT_KEY_PASSPHRASE
gpg --export "$FPR" > mseries/release/mseries-archive-keyring.gpg   # public half, committed
shred -u mseries-ci-subkey.asc                      # keep only the offline backup
```

Commit `mseries/release/mseries-archive-keyring.gpg` (public) and record the fingerprint in
`RELEASE-PIPELINE.md`. The next `mseries-update` build ships it as
`/usr/share/keyrings/mseries-archive-keyring.gpg` (`build.sh` includes it when the file exists), and
`mseries-update init --uri <repo> --keyring /usr/share/keyrings/mseries-archive-keyring.gpg` uses it.
Each publish also writes `apt/mseries-archive-keyring.{gpg,asc}` next to the suites: handy to compare
fingerprints, **not** a trust anchor (it comes from the same host as the packages).

## Check what CI will do

```bash
bash mseries/release/test-assemble.sh      # throwaway key, fake debs, real apt-get update
```

The workflow's publish job signs with whatever secret key `MSERIES_APT_KEY` imports, then verifies the
result with the exported public key before it commits anything.

## Rotate (before the one-year expiry, or after any suspicion of leak)

1. Create a new signing subkey (or a new key) offline; update the `MSERIES_APT_KEY` secret.
2. While the old key is still valid, ship a `mseries-update` build whose keyring contains **both** public
   keys, signed by the old key. Clients take it as a normal update.
3. Switch the secret to the new key only after clients have had a release cycle to receive the keyring.
4. A lost or leaked key with no overlap cannot be fixed by update: clients must re-run
   `mseries-update init` with a keyring obtained out of band. That is why the primary is backed up twice.

## Not covered

`Release` carries no `Valid-Until`, so a replayed old (still correctly signed) repository would be
accepted; the updater's own rule never to install a lower version limits the damage. Adding
`Valid-Until` needs a scheduled re-sign job, which is deferred until there are customers.
