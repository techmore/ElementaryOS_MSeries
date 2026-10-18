#!/usr/bin/python3
"""Real temporary Git-object packaging tests; no installed runtime or inference."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SOURCE = Path(__file__).with_name("package-f5.py")
SPEC = importlib.util.spec_from_file_location("package_f5", SOURCE)
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)
MODEL_SHA = "90d8c89714cd31efc88be62a40c6b2bea57e0cc2063af1ffe2c28f1a228ca110"
NATIVE_SHA = "9f1f839d89a6d3a874c939ecf3108007cc0964a338596a35adb47c7e6c5c921d"
MODEL_REPO = "handy-computer/nemotron-speech-streaming-en-0.6b-gguf"
REVISION = "7df420cc3fb915a3b334560dac712af44fc41ef5"


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="f5-package-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.command("init", "--quiet")
        self.command("config", "user.name", "Source package fixture")
        self.command("config", "user.email", "fixture@example.invalid")
        self.command("config", "core.autocrlf", "false")
        for source in package.FIXED_FILES.values():
            self.write(source, "# synthetic source-only fixture\n")
        self.write(package.PACKAGER, SOURCE.read_bytes())
        self.write(package.INSTALLER, self.installer())
        for name in package.RUNTIME_FILES:
            self.write("mseries/dictation/" + name, "# Synthetic " + name + "\n")
        self.write("mseries/dictation/dictation-engine.py", self.engine())
        self.write(package.TEMPLATES + "preflight.py", self.preflight())
        self.write(package.TEMPLATES + "install.sh", "#!/bin/sh\n# Synthetic wrapper\nexit 0\n")
        # Unwanted files are committed too, proving this is an allowlist export,
        # not Git archive of the full tree or an extension-based search.
        for name in ("mseries/dictation/voice-assistant.py", "mseries/dictation/dictation_voice.py",
                     "mseries/local-ai/diagnostic_agent.py", "mseries/mcp/private-profile.json",
                     "models/test.gguf", "native/libtranscribe.so", "audio/test.wav"):
            self.write(name, b"excluded\x00synthetic binary or private fixture\n")
        self.write("private-link", b"")
        (self.repo / "private-link").unlink()
        (self.repo / "private-link").symlink_to("/not-a-real-owner-file")
        (self.repo / package.TEMPLATES / "install.sh").chmod(0o755)
        self.commit = self.save()

    def command(self, *args):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_DATE="2000-01-01T00:00:00+00:00", GIT_COMMITTER_DATE="2000-01-01T00:00:00+00:00")
        for key in tuple(env):
            if key.startswith("GIT_") and key not in {
                "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"
            }:
                del env[key]
        result = subprocess.run(["git", "-C", str(self.repo), *args], env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, check=True)
        return result.stdout.decode().strip()

    def write(self, name, contents):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode() if isinstance(contents, str) else contents)

    def installer(self, names=None):
        values = sorted(package.RUNTIME_FILES) if names is None else names
        return ("RUNTIME_FILES = " + repr(tuple(values)) + "\n"
                "def download():\n    url = 'https://huggingface.co/" + MODEL_REPO + "/resolve/" + REVISION + "/'\n"
                "raise RuntimeError('The packager must never execute this fixture')\n")

    def engine(self):
        return "NEMOTRON = 'nemotron-speech-streaming-en-0.6b-Q8_0.gguf'\nNEMOTRON_SHA256 = '" + MODEL_SHA + "'\n"

    def preflight(self):
        return ("NATIVE_SHA256 = '" + NATIVE_SHA + "'\n"
                "def inspect():\n    metadata('transcribe-cpp', '0.4.0')\n    metadata('numpy', '2.5.4')\n")

    def save(self):
        self.command("add", "--all")
        self.command("commit", "--quiet", "-m", "Synthetic fixture")
        return self.command("rev-parse", "HEAD")

    def build(self, label="out", ref=None):
        destination = self.base / label
        result = package.build(self.repo, ref or self.commit, destination)
        return destination, result

    def archive(self, destination):
        with tarfile.open(destination / package.ARCHIVE, "r:gz") as archive:
            return {member.name.removeprefix(package.NAME + "/"): archive.extractfile(member).read()
                    for member in archive.getmembers()}

    def test_reproducible_bytes_normalized_tar_and_complete_integrity(self):
        first, provenance = self.build("first")
        old_umask = os.umask(0o077)
        try:
            with mock.patch.dict(os.environ, {"TZ": "Pacific/Kiritimati", "SOURCE_DATE_EPOCH": "999999999"}):
                second, second_provenance = self.build("second")
        finally:
            os.umask(old_umask)
        self.assertEqual(provenance, second_provenance)
        self.assertEqual(sorted(path.name for path in first.iterdir()),
                         ["SHA256SUMS", package.ARCHIVE, "provenance.json"])
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        raw = (first / package.ARCHIVE).read_bytes()
        self.assertEqual(raw[4:8], b"\x00\x00\x00\x00")  # gzip timestamp
        self.assertFalse(raw[3] & 8)  # no host/output-dependent original filename
        files = self.archive(first)
        manifest = json.loads(files["manifest.json"])
        self.assertEqual(manifest["version"], "0.0.1")
        self.assertEqual(manifest["scope"], "existingM1Pro32GBdesktopSTTonly")
        self.assertEqual(manifest["source_commit"], self.commit)
        self.assertEqual(set(manifest["files"]), set(files) - {"manifest.json"})
        for name, expected in manifest["files"].items():
            self.assertEqual(expected, hashlib.sha256(files[name]).hexdigest())
        self.assertEqual(provenance["manifest_sha256"], hashlib.sha256(files["manifest.json"]).hexdigest())
        self.assertEqual(provenance["archive"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(manifest["model"]["sha256"], MODEL_SHA)
        self.assertEqual(manifest["model"]["revision"], REVISION)
        self.assertFalse(manifest["model"]["distributed"])
        self.assertEqual(manifest["runtime"]["native_library_sha256"], NATIVE_SHA)
        self.assertFalse(manifest["runtime"]["distributed"])
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = archive.getmembers()
            self.assertEqual([item.name for item in members], sorted(item.name for item in members))
            for member in members:
                self.assertTrue(member.isfile())
                self.assertEqual((member.mtime, member.uid, member.gid, member.uname, member.gname), (0, 0, 0, "", ""))
                self.assertIn(member.mode, (0o644, 0o755))
                self.assertTrue(member.name.startswith(package.NAME + "/"))
                self.assertNotIn("..", member.name.split("/"))
                self.assertEqual(member.pax_headers, {})
        for line in (first / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split("  ", 1)
            self.assertEqual(expected, hashlib.sha256((first / name).read_bytes()).hexdigest())

    def test_exact_allowlist_excludes_committed_extras_index_and_worktree(self):
        first, _ = self.build("baseline")
        self.write(package.INSTALLER, "not valid Python and never committed\n")
        self.write("mseries/dictation/stream-dictate.py", "# staged but not selected\n")
        self.command("add", "mseries/dictation/stream-dictate.py")
        self.write(package.TEMPLATES + "README.md", "PRIVATE UNCOMMITTED NOTE\n")
        self.write("untracked-secret.txt", "PRIVATE UNTRACKED NOTE\n")
        # The exported builder itself must also be the committed blob.
        self.write(package.PACKAGER, "# ambient builder is excluded\n")
        second, _ = self.build("dirty")
        self.assertEqual((first / package.ARCHIVE).read_bytes(), (second / package.ARCHIVE).read_bytes())
        files = self.archive(second)
        expected = set(package.FIXED_FILES) | {"mseries/dictation/" + name for name in package.RUNTIME_FILES} | {"manifest.json"}
        self.assertEqual(set(files), expected)
        self.assertEqual(files["tools/package-f5.py"], SOURCE.read_bytes())
        self.assertNotIn(b"PRIVATE", b"".join(files.values()))
        self.assertFalse(any("voice-assistant" in name or name.endswith((".gguf", ".so", ".wav")) for name in files))

    def test_cli_derives_fixture_repository_and_does_not_accept_branch_or_short_sha(self):
        output = self.base / "cli"
        result = subprocess.run([sys.executable, str(self.repo / package.PACKAGER),
                                 "--source-ref", self.commit, "--output", str(output)],
                                cwd=self.base, capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(result.stdout)["published"])
        self.assertEqual(json.loads(result.stdout)["source_commit"], self.commit)
        self.assertEqual(json.loads(self.archive(output)["manifest.json"])["source_commit"], self.commit)
        for ref in ("HEAD", "main", self.commit[:12], self.commit.upper(), "-" * 40, "0" * 40):
            with self.subTest(ref=ref), self.assertRaises(package.PackageError):
                self.build("rejected", ref)
        tree_id = self.command("rev-parse", self.commit + "^{tree}")
        with self.assertRaises(package.PackageError):
            self.build("tree", tree_id)
        self.command("tag", "-a", "fixture-tag", "-m", "Annotated tag")
        tag_object = self.command("rev-parse", "fixture-tag")
        with self.assertRaises(package.PackageError):
            self.build("tag-object", tag_object)

    def test_runtime_ast_rejects_new_removed_duplicate_traversal_and_executable_entries(self):
        names = sorted(package.RUNTIME_FILES)
        for replacement in (names + ["voice-assistant.py"], names[:-1],
                            names[:-1] + [names[0]], names[:-1] + ["../voice-assistant.py"]):
            with self.subTest(entries=replacement), self.assertRaises(package.PackageError):
                package.runtime_names(self.installer(replacement).encode())
        for source in ("RUNTIME_FILES = tuple(['stream-dictate.py'])\n",
                       "RUNTIME_FILES = ()\nRUNTIME_FILES = ()\n",
                       "RUNTIME_FILES: tuple = ()\n"):
            with self.subTest(source=source), self.assertRaises(package.PackageError):
                package.runtime_names(source.encode())
        self.write(package.INSTALLER, self.installer(names[:-1] + ["voice-assistant.py"]))
        bad_commit = self.save()
        with self.assertRaises(package.PackageError):
            self.build("bad-runtime", bad_commit)
        self.assertFalse((self.base / "bad-runtime").exists())

    def test_committed_symlinks_and_gitlinks_refused_but_ambient_links_ignored(self):
        for index, name in enumerate(("LICENSE", package.TEMPLATES + "README.md", "mseries/dictation/dictation-input.py")):
            path = self.repo / name
            original = path.read_bytes()
            path.unlink()
            path.symlink_to("/not-a-real-owner-file")
            commit = self.save()
            with self.subTest(name=name), self.assertRaises(package.PackageError):
                self.build("symlink-" + str(index), commit)
            path.unlink()
            path.write_bytes(original)
            self.save()
        # A gitlink is not a regular source file, even with an allowed filename.
        self.command("update-index", "--add", "--cacheinfo", "160000," + self.commit + ",LICENSE")
        self.command("commit", "--quiet", "-m", "Synthetic gitlink")
        with self.assertRaises(package.PackageError):
            self.build("gitlink", self.command("rev-parse", "HEAD"))
        # An uncommitted link cannot influence the already selected base commit.
        (self.repo / "mseries/dictation/stream-dictate.py").unlink()
        (self.repo / "mseries/dictation/stream-dictate.py").symlink_to("/not-a-real-owner-file")
        output, _ = self.build("ambient-link")
        self.assertIn("mseries/dictation/stream-dictate.py", self.archive(output))

    def test_missing_template_binary_source_and_invalid_pins_fail_without_outputs(self):
        required = self.repo / package.TEMPLATES / "THIRD-PARTY.md"
        original = required.read_bytes()
        required.unlink()
        with self.assertRaises(package.PackageError):
            self.build("missing", self.save())
        required.write_bytes(original)
        self.write("mseries/dictation/stream-dictate.py", b"\x7fELF\x00not-source")
        with self.assertRaises(package.PackageError):
            self.build("binary", self.save())
        self.write("mseries/dictation/stream-dictate.py", "# synthetic source\n")
        self.write("mseries/dictation/dictation-engine.py", self.engine().replace(MODEL_SHA, "not-a-digest"))
        with self.assertRaises(package.PackageError):
            self.build("pin", self.save())
        for label in ("missing", "binary", "pin"):
            self.assertFalse((self.base / label).exists())

    def test_output_collision_symlinks_and_failed_publication_preserve_existing_bytes(self):
        output, _ = self.build()
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        with self.assertRaises(package.PackageError):
            self.build()
        self.assertEqual(original, {path.name: path.read_bytes() for path in output.iterdir()})
        linked = self.base / "linked-output"
        linked.symlink_to(output, target_is_directory=True)
        with self.assertRaises(package.PackageError):
            self.build("linked-output")
        broken = self.base / "broken-artifact"
        broken.mkdir()
        (broken / "provenance.json").symlink_to("/not-a-real-owner-file")
        with self.assertRaises(package.PackageError):
            self.build("broken-artifact")
        target = self.base / "publication-fails"
        real_link = os.link
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("Synthetic output interruption")
            return real_link(*args, **kwargs)
        with mock.patch.object(package.os, "link", side_effect=fail_second):
            with self.assertRaises(package.PackageError):
                self.build("publication-fails")
        self.assertEqual(list(target.iterdir()), [])

    def test_git_environment_cannot_redirect_to_another_index_worktree_or_repository(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": str(self.base / "does-not-exist"),
                                         "GIT_WORK_TREE": "/not-a-real-owner-file",
                                         "GIT_INDEX_FILE": "/not-a-real-owner-file",
                                         "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "alias.cat-file",
                                         "GIT_CONFIG_VALUE_0": "!false"}):
            output, _ = self.build("git-env")
        self.assertEqual(json.loads(self.archive(output)["manifest.json"])["source_commit"], self.commit)

    def test_only_explicit_app_launcher_helper_is_included_and_regular(self):
        helper = "mseries/dictation/enable-app-input.py"
        self.write(helper, "# Synthetic committed app launcher helper\n")
        self.write("mseries/dictation/enable-some-other-app.py", "# Not approved for this package\n")
        commit = self.save()
        destination, _ = self.build("launcher", commit)
        files = self.archive(destination)
        self.assertEqual(files[helper], b"# Synthetic committed app launcher helper\n")
        self.assertNotIn("mseries/dictation/enable-some-other-app.py", files)
        self.assertEqual(len(package.runtime_names(self.installer().encode())), 16)
        (self.repo / helper).unlink()
        (self.repo / helper).symlink_to("/not-a-real-owner-file")
        with self.assertRaises(package.PackageError):
            self.build("launcher-link", self.save())


if __name__ == "__main__":
    unittest.main()
