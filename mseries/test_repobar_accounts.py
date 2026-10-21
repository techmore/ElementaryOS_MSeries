#!/usr/bin/env python3
"""RepoBar multi-account behaviour, against a fake `gh` so no real sign-in or network is used."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().with_name("repobar.py")

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
if args[:2] == ["auth", "status"]:
    print("github.com\n  ✓ Logged in to github.com account alice (keyring)\n  - Active account: true\n"
          "  - Git operations protocol: https\n\ngithub.com\n  ✓ Logged in to github.com account bob (keyring)\n"
          "  - Active account: false\n\ncorp.example.com\n  ✓ Logged in to corp.example.com account carol (keyring)\n"
          "  - Active account: true\n\ngithub.com\n  X Failed to log in to github.com account dave (keyring)\n"
          "  - Active account: false")
elif args[:2] == ["auth", "token"]:
    user = args[args.index("--user") + 1]
    print("token-for-" + user)
elif args and args[0] == "api":
    with open(log, "a") as stream:
        stream.write(json.dumps({"args": args, "host": os.environ.get("GH_HOST"), "token": os.environ.get("GH_TOKEN"),
                                 "enterprise": os.environ.get("GH_ENTERPRISE_TOKEN")}) + "\n")
    print(json.dumps({"resources": {}}))
else:
    sys.exit(1)
"""


class RepoBarAccountsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "bin").mkdir()
        gh = root / "bin" / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = root / "gh.log"
        self.env = dict(os.environ, HOME=str(root), PATH=f"{root / 'bin'}:{os.environ['PATH']}", FAKE_GH_LOG=str(self.log))
        self.settings = root / ".config/mseries/repobar/settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_helper(self, *args, check=True):
        result = subprocess.run([sys.executable, str(HELPER), "--json", *args], env=self.env, capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_lists_accounts_and_skips_failed_logins(self):
        accounts = json.loads(self.run_helper("auth", "accounts").stdout)["accounts"]
        self.assertEqual([(a["login"], a["host"], a["active"]) for a in accounts],
                         [("alice", "github.com", True), ("bob", "github.com", False), ("carol", "corp.example.com", True)])

    def test_status_follows_cli_until_an_account_is_chosen(self):
        status = json.loads(self.run_helper("auth", "status").stdout)
        self.assertEqual((status["account"], status["followsCli"], status["authenticated"]), ("alice", True, True))
        self.run_helper("auth", "use", "bob")
        status = json.loads(self.run_helper("auth", "status").stdout)
        self.assertEqual((status["account"], status["followsCli"], status["authenticated"]), ("bob", False, True))
        self.run_helper("auth", "use", "")
        self.assertTrue(json.loads(self.run_helper("auth", "status").stdout)["followsCli"])

    def test_use_account_at_host_switches_host_too(self):
        self.run_helper("auth", "use", "carol@corp.example.com")
        saved = json.loads(self.settings.read_text())
        self.assertEqual((saved["account"], saved["host"]), ("carol", "corp.example.com"))

    def test_unknown_account_is_refused_and_nothing_is_saved(self):
        result = self.run_helper("auth", "use", "mallory", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not signed in", json.loads(result.stdout)["error"])
        self.assertFalse(self.settings.exists())

    def test_api_calls_run_as_the_chosen_account(self):
        self.run_helper("auth", "use", "bob")
        self.run_helper("rate-limits", "--refresh")
        call = self.calls()[-1]
        self.assertEqual((call["host"], call["token"]), ("github.com", "token-for-bob"))

    def test_enterprise_host_uses_enterprise_token(self):
        self.run_helper("auth", "use", "carol@corp.example.com")
        self.run_helper("rate-limits", "--refresh")
        call = self.calls()[-1]
        self.assertEqual((call["host"], call["enterprise"], call["token"]), ("corp.example.com", "token-for-carol", None))

    def test_following_the_cli_passes_no_token(self):
        self.run_helper("rate-limits", "--refresh")
        self.assertIsNone(self.calls()[-1]["token"])

    def test_api_cache_is_per_account(self):
        self.run_helper("rate-limits")
        self.run_helper("auth", "use", "bob")
        self.run_helper("rate-limits")
        self.assertEqual(len(self.calls()), 2)

    def test_snapshot_cache_from_another_account_is_ignored(self):
        cache = Path(self.tmp.name) / ".cache/mseries/repobar/snapshot.json"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({"schemaVersion": 1, "account": "alice", "host": "github.com",
                                     "fetchedAt": 2**31, "repos": []}))
        self.run_helper("auth", "use", "bob")
        code = ("import sys; sys.path.insert(0, %r); import repobar; print(repobar.read_cache() is None)" % str(HELPER.parent))
        out = subprocess.run([sys.executable, "-c", code], env=self.env, capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, "True")


if __name__ == "__main__":
    unittest.main()
