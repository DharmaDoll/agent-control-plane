import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/file_setting.py"


class UserSettings(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def call(self, tool, path, *args, ok=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), tool, str(path), *args],
            env={**os.environ, "HOME": str(self.home)}, text=True, capture_output=True)
        self.assertNotIn("credential-fixture", result.stdout + result.stderr)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)

    def test_all_new_configs(self):
        for tool, name, entry in [
            ("bun", ".bunfig.toml", "minimumReleaseAge = 604800"),
            ("uv", "uv.toml", 'exclude-newer = "7 days"'),
            ("cargo", "config.toml", 'global-min-publish-age = "7 days"'),
            ("gem", ".gemrc", ":cooldown: 7"),
        ]:
            with self.subTest(tool=tool):
                path = self.home / tool / name
                review = self.call(tool, path)["review"]
                self.assertFalse(path.parent.exists())
                self.call(tool, path, "--apply", review)
                self.assertIn(entry, path.read_text())
                before = path.read_bytes()
                self.call(tool, path, "--apply", review, ok=False)
                self.assertEqual(before, path.read_bytes())

    def test_stale_preview_then_preserve_existing_table_and_mode(self):
        path = self.home / ".bunfig.toml"
        path.write_text('[install]\nregistry = "credential-fixture"\n')
        path.chmod(0o600)
        token = self.call("bun", path)["review"]
        with path.open("a") as stream:
            stream.write("# concurrent change\n")
        before = path.read_text()
        self.call("bun", path, "--apply", token, ok=False)
        self.assertEqual(before, path.read_text())
        self.call("bun", path, "--apply", self.call("bun", path)["review"])
        self.assertIn("# concurrent change", path.read_text())
        self.assertIn('registry = "credential-fixture"', path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_explicit_disable_malformed_file_and_symlink(self):
        path = self.home / ".bunfig.toml"
        for data in ('[install]\nminimumReleaseAge = 0', 'invalid credential-fixture'):
            path.write_text(data)
            self.call("bun", path, ok=False)
            self.assertEqual(data, path.read_text())
        path.unlink()
        other = self.home / "other"
        other.touch()
        path.symlink_to(other)
        self.call("bun", path, ok=False)
        self.assertEqual(other.read_bytes(), b"")
