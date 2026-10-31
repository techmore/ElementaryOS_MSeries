#!/usr/bin/env python3
"""codexbar_install_cli_compat: the libxml2 shim must follow upstream upgrades and remove itself
once the CLI no longer links libxml2.so.2 (upstream v0.79.0+)."""

import os
import pathlib
import subprocess
import tempfile
import unittest

LIB_SH = pathlib.Path(__file__).with_name("lib-codexbar.sh")
# Fake binaries; the stub below reports libxml2 for any file containing "needs-libxml2".
OLD = b"\x7fELF v0.78.0 needs-libxml2"
NEW = b"\x7fELF v0.83.0"
NEW_NEEDS = b"\x7fELF v0.8x needs-libxml2"


class CliCompat(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = pathlib.Path(self.temp.name)
        self.home = root / "home"
        self.lib = self.home / ".local/lib/codexbar-cli"
        self.lib.mkdir(parents=True)
        shims = root / "bin"
        shims.mkdir()
        # A base that ships only the renamed libxml2 soname, like Ubuntu 26.04.
        (shims / "ldconfig").write_text(
            "#!/bin/sh\nprintf '\\tlibxml2.so.16 (libc6,AArch64) => /usr/lib/libxml2.so.16\\n'\n")
        (shims / "ldconfig").chmod(0o755)
        self.path = f"{shims}:{os.environ['PATH']}"

    def compat(self):
        script = (f'source "{LIB_SH}"\n'
                  'codexbar_cli_needs_libxml2() { grep -q needs-libxml2 "$1"; }\n'
                  'codexbar_install_cli_compat\n')
        subprocess.run(["bash", "-c", script], check=True,
                       env={**os.environ, "HOME": str(self.home), "PATH": self.path})

    def install(self, payload, symlink=True):
        """install-codexbar.sh: extract the tarball into lib, then move codexbar over codexbar-upstream.
        Upstream's tarball ships codexbar as a symlink to CodexBarCLI."""
        extracted = self.lib / "codexbar"
        if symlink:
            (self.lib / "CodexBarCLI").write_bytes(payload)
            extracted.symlink_to("CodexBarCLI")
        else:
            extracted.write_bytes(payload)
        os.replace(extracted, self.lib / "codexbar-upstream")

    def executes(self):
        """Bytes of the binary codexbar-upstream ends up running."""
        upstream = self.lib / "codexbar-upstream"
        if not upstream.is_symlink() and upstream.read_bytes().startswith(b"#!"):
            text = upstream.read_text()
            self.assertIn("compat", text)
            return (self.lib / (self.lib / "codexbar-upstream.real").read_text().strip()).read_bytes()
        return upstream.read_bytes()

    def assert_no_shim(self):
        for leftover in ("codexbar-upstream.real", "codexbar-upstream.bin", "compat"):
            self.assertFalse((self.lib / leftover).exists(), leftover)

    def test_cli_that_links_libxml2_gets_the_wrapper(self):
        self.install(OLD)
        self.compat()

        self.assertTrue((self.lib / "compat/libxml2.so.2").is_symlink())
        self.assertEqual((self.lib / "codexbar-upstream.real").read_text().strip(), "CodexBarCLI")
        self.assertEqual(self.executes(), OLD)

    def test_rerun_on_wrapper_is_idempotent(self):
        self.install(OLD)
        self.compat()
        wrapper = (self.lib / "codexbar-upstream").read_bytes()

        self.compat()

        self.assertEqual((self.lib / "codexbar-upstream").read_bytes(), wrapper)
        self.assertEqual(self.executes(), OLD)

    def test_upgrade_to_cli_without_libxml2_removes_the_shim(self):
        self.install(OLD)
        self.compat()

        self.install(NEW)
        self.compat()

        self.assertTrue((self.lib / "codexbar-upstream").is_symlink())
        self.assertEqual(self.executes(), NEW)
        self.assert_no_shim()

    def test_wrapper_left_over_a_replaced_binary_is_retired(self):
        # A v0.83.0 tarball extracted over CodexBarCLI while the wrapper stayed (the previous
        # code's upgrade result): the next deploy points codexbar-upstream at the binary directly.
        self.install(OLD)
        self.compat()
        (self.lib / "CodexBarCLI").write_bytes(NEW)

        self.compat()

        self.assertTrue((self.lib / "codexbar-upstream").is_symlink())
        self.assertEqual(self.executes(), NEW)
        self.assert_no_shim()

    def test_plain_binary_upgrade_that_still_needs_libxml2_wraps_the_new_binary(self):
        self.install(OLD, symlink=False)
        self.compat()
        self.assertEqual((self.lib / "codexbar-upstream.real").read_text().strip(), "codexbar-upstream.bin")

        self.install(NEW_NEEDS, symlink=False)
        self.compat()

        self.assertEqual(self.executes(), NEW_NEEDS)

    def test_plain_binary_upgrade_without_libxml2_drops_the_old_binary(self):
        self.install(OLD, symlink=False)
        self.compat()

        self.install(NEW, symlink=False)
        self.compat()
        self.compat()

        self.assertEqual(self.executes(), NEW)
        self.assert_no_shim()


if __name__ == "__main__":
    unittest.main()
