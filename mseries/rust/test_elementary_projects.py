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
                self.assertIn(
                    repository["scope_status"],
                    {"review-required", "image-package-source-candidate", "detailed-source-record", "build-source-input"},
                )

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
                self.assertTrue(project["license"]["evidence"])
                if project["license"]["spdx"] is None:
                    self.assertEqual(project["rust_status"], "source-license-unverified")
                    self.assertRegex(project["license"]["evidence"], r"(?i)no license|unverified")
                else:
                    self.assertRegex(project["license"]["spdx"], r"^(?:GPL|LGPL)-[0-9.]+(?:-or-later)?$")
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

    def test_image_metapackage_projects_have_independent_rust_records(self):
        manifest = json.loads((Path(__file__).with_name("elementary-image-projects.json")).read_text())
        projects = manifest["projects"]
        self.assertEqual(manifest["project_count"], len(projects))
        self.assertEqual(len(projects), 59)
        self.assertEqual(len({project["repository"] for project in projects}), len(projects))
        census = json.loads((Path(__file__).with_name("elementary-org-census.json")).read_text())
        census_names = {
            name
            for repository in census["repositories"]
            for name in [repository["name"], *repository.get("repository_aliases", [])]
        }
        aliases = {
            alias: repository["name"]
            for repository in census["repositories"]
            for alias in repository.get("repository_aliases", [])
        }
        detailed_names = {
            aliases.get(project["id"].split("/", 1)[1], project["id"].split("/", 1)[1])
            for project in REGISTER["projects"]
        }
        self.assertTrue(detailed_names.issubset({project["repository"] for project in projects}))
        self.assertTrue({project["repository"] for project in projects}.issubset(census_names))
        self.assertTrue(all(project["image_presence_status"] for project in projects))
        for project in projects:
            with self.subTest(image_project=project["repository"]):
                self.assertTrue(project["packages"])
                self.assertTrue(project["source_files"])
                self.assertTrue(project["rust_migration_status"])
                self.assertTrue(project["rust_project_target"])
                self.assertTrue(project["repository_mapping_status"])
                self.assertTrue(project["source_pin_status"])
                self.assertTrue(project["license_status"])

        for source_file in manifest["upstream_metapackages"]["seed_files"]:
            self.assertTrue(source_file["blob_sha"])
            self.assertIn(source_file["path"], {"desktop-arm64", "desktop-recommends-arm64", "pantheon-recommends-arm64", "pantheon-shell-arm64"})


if __name__ == "__main__":
    unittest.main()
