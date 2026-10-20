#!/usr/bin/env python3
"""Validate one independent source and Rust migration record per core project."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
REGISTER = json.loads((Path(__file__).with_name("elementary-projects.json")).read_text())
REQUIRED = {
    "elementary/os",
    "elementary/gala",
    "elementary/wingpanel",
    "elementary/dock",
    "elementary/files",
    "elementary/quick-settings",
    "elementary/panel-network",
    "elementary/panel-power",
    "elementary/wingpanel-indicator-sound",
    "elementary/panel-keyboard",
}


class ElementaryProjectRegister(unittest.TestCase):
    def test_each_core_repo_has_a_separate_complete_record(self):
        projects = REGISTER["projects"]
        ids = [project["id"] for project in projects]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(REQUIRED.issubset(set(ids)))
        census = json.loads((Path(__file__).with_name("elementary-org-census.json")).read_text())
        repositories = census["repositories"]
        names = [repository["name"] for repository in repositories]
        self.assertEqual(census["repository_count"], len(repositories))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(repositories), 153)
        census_by_name = {
            name: repository
            for repository in repositories
            for name in [repository["name"], *repository.get("repository_aliases", [])]
        }

        for repository in repositories:
            with self.subTest(census_repository=repository["name"]):
                self.assertEqual(repository["url"], f"https://github.com/elementary/{repository['name']}")
                self.assertTrue(repository["default_branch"])
                self.assertEqual(repository["scope_status"], "review-required")

        registered_names = {project_id.split("/", 1)[1] for project_id in ids}
        self.assertTrue(registered_names.issubset(census_by_name))
        people = json.loads((ROOT / "mseries/local-ai/people-watch.json").read_text())
        branches = json.loads((ROOT / "mseries/local-ai/branch-watch.json").read_text())["sources"]
        people_repos = {item["repo"] for item in people if "repo" in item}
        branch_repos = {item["repo"] for item in branches}

        for project in projects:
            with self.subTest(project=project["id"]):
                self.assertEqual(project["url"], f"https://github.com/{project['id']}")
                self.assertIn(project["id"], people_repos)
                self.assertIn(project["id"], branch_repos)
                self.assertRegex(project["license"]["spdx"], r"^(?:GPL|LGPL)-[0-9.]+(?:-or-later)?$")
                self.assertTrue(project["license"]["evidence"])
                self.assertTrue(project["pin"]["value"])
                self.assertTrue(project["rust_target"])
                self.assertTrue(project["parity_contract"])
                self.assertIsInstance(project["intentional_enhancements"], list)
                pin_locations = list(project["pin"].get("consumers", []))
                if project["pin"].get("record"):
                    pin_locations.append(project["pin"]["record"])
                self.assertTrue(pin_locations, "pin needs an authoritative source file")
                for relative_path in pin_locations:
                    self.assertIn(project["pin"]["value"], (ROOT / relative_path).read_text())


if __name__ == "__main__":
    unittest.main()
