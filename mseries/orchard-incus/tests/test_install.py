"""install.sh in a throwaway HOME: idempotent, keeps one backup of the replaced code, uninstalls cleanly.
Never touches the real ~/.local (HOME and XDG_DATA_HOME point at a temp dir)."""
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "install.sh")
ID = "io.github.techmore.OrchardIncus"


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.env = {**os.environ, "HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, ".local/share"),
                    "PATH": os.environ["PATH"]}
        self.share = os.path.join(self.home, ".local/share")

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args):
        return subprocess.run(["sh", SCRIPT, *args], env=self.env, capture_output=True, text=True, timeout=60)

    def pkg(self, *p):
        return os.path.join(self.share, "orchard-incus", *p)

    def test_install_twice_is_idempotent_and_keeps_a_backup(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.pkg("orchard_incus", "backend.py")))
        self.assertTrue(os.access(os.path.join(self.home, ".local/bin/orchard-incus"), os.X_OK))
        with open(os.path.join(self.share, "applications", ID + ".desktop")) as f:
            self.assertIn("Exec=" + os.path.join(self.home, ".local/bin/orchard-incus"), f.read())
        self.assertFalse(os.path.exists(self.pkg("orchard_incus.prev")), "no backup on a first install")
        # a locally edited copy must be preserved as the backup on re-install
        with open(self.pkg("orchard_incus", "marker.txt"), "w") as f:
            f.write("old")
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.pkg("orchard_incus.prev", "marker.txt")))
        self.assertFalse(os.path.exists(self.pkg("orchard_incus", "marker.txt")))
        self.assertTrue(os.path.isfile(self.pkg("orchard_incus", "backend.py")))
        self.assertFalse(os.path.exists(self.pkg("orchard_incus.new")))

    def test_failed_copy_leaves_the_working_install_alone(self):
        self.assertEqual(self.run_install().returncode, 0)
        os.makedirs(self.pkg("orchard_incus.new"), exist_ok=True)  # stale staging dir from a crashed run
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(self.pkg("orchard_incus", "backend.py")))

    def test_uninstall(self):
        self.run_install()
        r = self.run_install("--uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.pkg()))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".local/bin/orchard-incus")))


if __name__ == "__main__":
    unittest.main()
