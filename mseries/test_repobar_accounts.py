#!/usr/bin/env python3
"""RepoBar multi-account behaviour, against a fake `gh` so no real sign-in or network is used."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HELPER = Path(__file__).resolve().with_name("repobar.py")

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
active = os.environ.get("FAKE_ACTIVE", "alice")
if args[:2] == ["auth", "status"]:
    if os.environ.get("FAKE_SIGNED_OUT"): sys.exit(1)
    if os.environ.get("FAKE_NETWORK_DOWN"):
        print("github.com\n  X Failed to log in to github.com account alice (keyring)\n  - Active account: true\n"
              "  - The token in keyring is invalid.")
        sys.exit(1)
    if os.environ.get("FAKE_BOB_EXPIRED"):
        print("github.com\n  ✓ Logged in to github.com account alice (keyring)\n  - Active account: false\n\n"
              "github.com\n  X Failed to log in to github.com account bob (keyring)\n  - Active account: true")
        sys.exit(1)
    print(f"github.com\n  ✓ Logged in to github.com account alice (keyring)\n  - Active account: {str(active == 'alice').lower()}\n"
          "  - Git operations protocol: https\n\ngithub.com\n  ✓ Logged in to github.com account bob (keyring)\n"
          f"  - Active account: {str(active == 'bob').lower()}\n\ncorp.example.com\n  ✓ Logged in to corp.example.com account carol (keyring)\n"
          "  - Active account: true\n\ngithub.com\n  X Failed to log in to github.com account dave (keyring)\n"
          "  - Active account: false")
elif args[:2] == ["auth", "token"]:
    user = args[args.index("--user") + 1]
    print("token-for-" + user)
elif args and args[0] == "api":
    with open(log, "a") as stream:
        stream.write(json.dumps({"args": args, "host": os.environ.get("GH_HOST"), "token": os.environ.get("GH_TOKEN"),
                                 "enterprise": os.environ.get("GH_ENTERPRISE_TOKEN")}) + "\n")
    if os.environ.get("FAKE_FAIL_API"): sys.exit(1)
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

    def test_following_the_cli_pins_the_resolved_account_token(self):
        self.run_helper("rate-limits", "--refresh")
        self.assertEqual(self.calls()[-1]["token"], "token-for-alice")

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

    def cached_snapshot(self, account="alice", host="github.com"):
        cache = Path(self.tmp.name) / ".cache/mseries/repobar/snapshot.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"schemaVersion": 1, "account": account, "host": host,
                                     "fetchedAt": 2**31, "repos": []}))

    def test_follow_cli_switch_rejects_other_accounts_snapshot(self):
        self.cached_snapshot("alice")
        self.env["FAKE_ACTIVE"] = "bob"
        self.env["FAKE_FAIL_API"] = "1"
        result = self.run_helper("snapshot", check=False)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('"account": "alice"', result.stdout)
        self.assertNotIn('"repos"', result.stdout)

    def test_follow_cli_switch_does_not_reuse_endpoint_cache(self):
        self.run_helper("rate-limits")
        self.env["FAKE_ACTIVE"] = "bob"
        self.run_helper("rate-limits")
        self.assertEqual([c["token"] for c in self.calls()], ["token-for-alice", "token-for-bob"])
        self.run_helper("auth", "use", "bob")
        self.run_helper("rate-limits")
        self.assertEqual(len(self.calls()), 2)  # Same resolved identity shares its own cache.

    def test_signed_out_does_not_fall_back_to_old_snapshot(self):
        self.cached_snapshot()
        self.env["FAKE_SIGNED_OUT"] = "1"
        self.assertEqual(self.run_helper("snapshot", check=False).returncode, 1)
        self.assertEqual(self.calls(), [])

    def test_network_down_keeps_showing_the_stale_snapshot(self):
        self.cached_snapshot("alice")
        self.env["FAKE_NETWORK_DOWN"] = "1"
        result = json.loads(self.run_helper("--refresh", "snapshot").stdout)
        self.assertTrue(result["stale"])
        self.assertEqual(result["account"], "alice")
        self.assertIn("last snapshot", result["error"])

    def test_network_down_never_shows_another_accounts_snapshot(self):
        self.cached_snapshot("bob")
        self.env["FAKE_NETWORK_DOWN"] = "1"
        self.assertEqual(self.run_helper("snapshot", check=False).returncode, 1)

    def test_active_flag_of_a_failed_login_is_not_credited_to_the_previous_account(self):
        self.env["FAKE_BOB_EXPIRED"] = "1"
        accounts = json.loads(self.run_helper("auth", "accounts").stdout)["accounts"]
        self.assertEqual([(a["login"], a["active"]) for a in accounts], [("alice", False)])

    def test_same_account_can_use_stale_snapshot_on_network_error(self):
        self.cached_snapshot("ALICE")
        self.env["FAKE_FAIL_API"] = "1"
        result = json.loads(self.run_helper("--refresh", "snapshot").stdout)
        self.assertTrue(result["stale"])
        self.assertEqual(result["account"], "ALICE")

    def test_host_change_rejects_snapshot(self):
        self.cached_snapshot()
        self.run_helper("auth", "use", "carol@corp.example.com")
        self.env["FAKE_FAIL_API"] = "1"
        self.assertEqual(self.run_helper("snapshot", check=False).returncode, 1)

    def test_inherited_token_cannot_override_selected_identity(self):
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            self.env[key] = "unrelated-fixture-token"
        self.run_helper("auth", "use", "bob")
        self.run_helper("rate-limits", "--refresh")
        self.assertEqual(self.calls()[-1]["token"], "token-for-bob")
        self.assertIsNone(self.calls()[-1]["enterprise"])

    def test_viewer_mismatch_cannot_be_cached(self):
        code = ("import sys;sys.path.insert(0,%r);import repobar;"
                "repobar._identity=lambda:('github.com','alice');"
                "repobar._repository_ids=lambda:('bob',[]);repobar.fetch_and_cache()" % str(HELPER.parent))
        result = subprocess.run([sys.executable, "-c", code], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different account", result.stderr)
        self.assertFalse((Path(self.tmp.name) / ".cache/mseries/repobar/snapshot.json").exists())

    def test_indicator_never_reads_unvalidated_disk_snapshot(self):
        source = HELPER.with_name("repobar-wingpanel").joinpath("Indicator.vala").read_text()
        self.assertNotIn('FileUtils.get_contents (Environment.get_home_dir () + "/.cache/mseries/repobar/snapshot.json"', source)
        self.assertIn("generation == settings_generation && panel_enabled", source)
        self.assertIn('settings_generation++;', source)

    def test_show_in_panel_defaults_on_and_round_trips(self):
        self.assertTrue(json.loads(self.run_helper("settings", "show").stdout)["showInPanel"])
        self.run_helper("settings", "set", "show-in-panel", "false")
        self.assertFalse(json.loads(self.settings.read_text())["showInPanel"])
        self.assertEqual(self.run_helper("settings", "set", "show-in-panel", "maybe", check=False).returncode, 1)


class RepoBarSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("repobar_snapshot_tests", HELPER)
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)
        cls.now = 1_800_000_000
        cls.recent = cls.helper.datetime.fromtimestamp(cls.now, cls.helper.timezone.utc).isoformat().replace("+00:00", "Z")

    def repository(self, name, **extra):
        return {"name": name, "repoState": "visible", "archived": False, "fork": False,
                "updatedAt": self.recent, **extra}

    def run_record(self, number):
        return {"id": number, "name": "Build", "head_branch": "feature", "event": "pull_request",
                "status": "in_progress", "created_at": self.recent, "updated_at": self.recent,
                "html_url": f"https://github.com/team/app/actions/runs/{number}"}

    def test_successful_empty_is_distinct_from_failed_and_not_checked(self):
        def query(argv):
            if "team/failed/" in argv[0]:
                raise RuntimeError("private credential diagnostic must not escape")
            return subprocess.CompletedProcess(argv, 0, json.dumps({"total_count": 0, "workflow_runs": []}))
        repos = [self.repository("team/empty"), self.repository("team/failed"),
                 self.repository("team/hidden", repoState="hidden")]
        with mock.patch.object(self.helper, "_run_gh", side_effect=query) as run:
            result = self.helper._workflow_runs(repos, self.now)
        observations = {o["repo"]: o for o in result["observations"]}
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result["checkedRepos"], 2)
        self.assertEqual(observations["team/empty"]["state"], "empty")
        self.assertEqual(observations["team/empty"]["totalCount"], 0)
        self.assertFalse(observations["team/empty"]["queryTruncated"])
        self.assertEqual(observations["team/failed"]["state"], "error")
        self.assertIsNone(observations["team/failed"]["totalCount"])
        self.assertEqual(observations["team/hidden"]["state"], "not_checked")
        self.assertIsNone(observations["team/hidden"]["fetchedAt"])
        self.assertNotIn("credential", json.dumps(result))

    def test_query_and_snapshot_caps_are_reported_per_repository(self):
        payload = {"total_count": 20, "workflow_runs": [self.run_record(i + 1) for i in range(15)]}
        with mock.patch.object(self.helper, "_run_gh", return_value=subprocess.CompletedProcess([], 0, json.dumps(payload))):
            result = self.helper._workflow_runs([self.repository(f"team/app{i}") for i in range(4)], self.now)
        self.assertEqual(len(result["running"]), 50)
        self.assertTrue(result["snapshotTruncated"])
        self.assertTrue(all(o["queryTruncated"] for o in result["observations"]))
        self.assertEqual([o["returnedCount"] for o in result["observations"]], [15] * 4)
        self.assertEqual(sum(o["displayedCount"] for o in result["observations"]), 50)
        self.assertTrue(any(o["snapshotTruncated"] for o in result["observations"]))
        self.assertEqual(result["running"][0]["branch"], "feature")
        self.assertEqual(result["running"][0]["event"], "pull_request")

    def test_repository_bound_and_skipped_reasons_are_explicit(self):
        repos = [self.repository(f"team/app{i}") for i in range(31)]
        repos += [self.repository("team/fork", fork=True), self.repository("team/archive", archived=True),
                  self.repository("team/old", updatedAt="2000-01-01T00:00:00Z")]
        payload = json.dumps({"total_count": 0, "workflow_runs": []})
        with mock.patch.object(self.helper, "_run_gh", return_value=subprocess.CompletedProcess([], 0, payload)) as run:
            result = self.helper._workflow_runs(repos, self.now)
        self.assertEqual(run.call_count, 30)
        self.assertEqual([o["reason"] for o in result["observations"][-4:]],
                         ["repository_limit", "fork", "archived", "inactive"])

    def test_malformed_actions_response_is_not_a_successful_empty(self):
        for payload in [{"workflow_runs": None}, {"total_count": 0, "workflow_runs": [self.run_record(1)]},
                        {"workflow_runs": [None]}, []]:
            with self.subTest(payload=payload), mock.patch.object(self.helper, "_run_gh",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(payload))):
                result = self.helper._workflow_runs([self.repository("team/app")], self.now)
            self.assertEqual(result["observations"][0]["state"], "error")
            self.assertEqual(result["observations"][0]["reason"], "invalid_response")
        with mock.patch.object(self.helper, "_run_gh",
                return_value=subprocess.CompletedProcess([], 0, '{"workflow_runs": []}')):
            result = self.helper._workflow_runs([self.repository("team/app")], self.now)
        self.assertEqual(result["observations"][0]["state"], "success")
        self.assertIsNone(result["observations"][0]["totalCount"])
        self.assertIsNone(result["observations"][0]["queryTruncated"])

    def test_absent_malformed_and_zero_graphql_counts_survive_normalization(self):
        nodes = [{"nameWithOwner": "team/missing"},
                 {"nameWithOwner": "team/invalid", "openIssues": {"totalCount": "2"},
                  "openPullRequests": {"totalCount": -1}},
                 {"nameWithOwner": "team/zero", "openIssues": {"totalCount": 0},
                  "openPullRequests": {"totalCount": 3}}]
        with mock.patch.multiple(self.helper,
                _identity=mock.Mock(return_value=("github.com", "alice")),
                _repository_ids=mock.Mock(return_value=("alice", ["a"])),
                _repository_details=mock.Mock(return_value=nodes),
                _pages_repositories=mock.Mock(return_value=set()),
                _for_you=mock.Mock(return_value={}), _contributions=mock.Mock(return_value={}),
                load_settings=mock.Mock(return_value={}), _api_json=mock.Mock(return_value=({}, self.now)),
                _workflow_runs=mock.Mock(return_value={})):
            result = self.helper.fetch_snapshot()
        repos = {repo["name"]: repo for repo in result["repos"]}
        self.assertIsNone(repos["team/missing"]["openIssues"])
        self.assertIsNone(repos["team/missing"]["openPullRequests"])
        self.assertIsNone(repos["team/invalid"]["openIssues"])
        self.assertIsNone(repos["team/invalid"]["openPullRequests"])
        self.assertEqual(repos["team/zero"]["openIssues"], 0)
        self.assertEqual(repos["team/zero"]["openPullRequests"], 3)
        for invalid in [None, True, -1, 2.5, "3"]:
            self.assertIsNone(self.helper._optional_count(invalid))
        # Presentation/sorting must remain usable with unknown measurements.
        selected = self.helper.filter_repositories(
            {"repos": result["repos"], "settings": {"showArchived": True}}, scope="all", sort="issues")
        self.assertEqual(selected[0]["name"], "team/zero")
        self.assertIn("?", self.helper._human_table(result["repos"]))


if __name__ == "__main__":
    unittest.main()
