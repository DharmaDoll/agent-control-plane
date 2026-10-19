"""Offline checks using disposable repositories; no GitHub credentials required."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "check_target.py"
spec = importlib.util.spec_from_file_location("check_target", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="controlled-github-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(HOME=str(self.base), XDG_CONFIG_HOME=str(self.base),
                        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                        GIT_CONFIG_GLOBAL=os.devnull, PYTHONDONTWRITEBYTECODE="1")
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", "https://github.com/owner/repo.git")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], env=self.env,
                              capture_output=True, check=True, timeout=10).stdout

    def args(self, **overrides):
        values = dict(root=str(self.root), remote="origin", host="github.com",
                      repo="owner/repo", transport="https")
        values.update(overrides)
        return [part for key, value in values.items() for part in (f"--{key}", str(value))]

    def run_check(self, expected="PASS", reason=None, script=SCRIPT, **overrides):
        result = subprocess.run([sys.executable, "-B", str(script), *self.args(**overrides)],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0 if expected == "PASS" else 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], expected)
        if reason:
            self.assertEqual(payload["reason"], reason)
        return result

    def test_https_optional_suffix(self):
        for url in ("https://github.com/owner/repo", "https://github.com/owner/repo.git"):
            with self.subTest(url=url):
                self.git("remote", "set-url", "origin", url)
                self.run_check()

    def test_ssh_forms(self):
        for url in ("git@github.com:owner/repo.git", "ssh://git@github.com/owner/repo"):
            with self.subTest(url=url):
                self.git("remote", "set-url", "origin", url)
                self.run_check(transport="ssh")

    def test_host_case_and_expected_suffix(self):
        self.run_check(host="GitHub.com", repo="owner/repo.git")

    def test_linked_worktree(self):
        self.git("commit", "--allow-empty", "-m", "fixture")
        linked = self.base / "linked"
        self.git("worktree", "add", "-b", "topic", str(linked))
        self.run_check(root=linked)

    def test_subdirectory_not_root(self):
        nested = self.root / "nested"
        nested.mkdir()
        self.run_check("BLOCKED", "ROOT_MISMATCH", root=nested)

    def test_non_repository(self):
        self.run_check("BLOCKED", "GIT_CHECK_FAILED", root=self.base)

    def test_missing_root(self):
        self.run_check("BLOCKED", "CHECK_UNAVAILABLE", root=self.base / "missing")

    def test_target_mismatches(self):
        for override in (dict(host="other.example"), dict(repo="other/repo"), dict(transport="ssh")):
            with self.subTest(override=override):
                self.run_check("BLOCKED", "TARGET_MISMATCH", **override)

    def test_missing_remote(self):
        self.run_check("BLOCKED", "GIT_CHECK_FAILED", remote="missing")

    def test_multiple_fetch_urls(self):
        self.git("config", "--add", "remote.origin.url", "https://github.com/owner/other")
        self.run_check("BLOCKED", "MULTIPLE_OR_MISSING_URLS")

    def test_multiple_push_urls(self):
        for name in ("repo", "other"):
            self.git("config", "--add", "remote.origin.pushurl", f"https://github.com/owner/{name}")
        self.run_check("BLOCKED", "MULTIPLE_OR_MISSING_URLS")

    def test_fetch_push_mismatch(self):
        self.git("config", "remote.origin.pushurl", "git@github.com:owner/repo.git")
        self.run_check("BLOCKED", "FETCH_PUSH_MISMATCH")

    def test_equivalent_fetch_push_urls(self):
        self.git("config", "remote.origin.pushurl", "https://GITHUB.com/owner/repo")
        self.run_check()

    def test_mirror(self):
        self.git("config", "remote.origin.mirror", "true")
        self.run_check("BLOCKED", "MIRROR_REMOTE")
        self.git("config", "remote.origin.mirror", "false")
        self.run_check()

    def test_invalid_mirror_boolean(self):
        self.git("config", "remote.origin.mirror", "invalid")
        self.run_check("BLOCKED", "GIT_CHECK_FAILED")

    def test_instead_of_rewrite(self):
        self.git("config", "url.https://other.example/.insteadOf", "https://github.com/")
        self.run_check("BLOCKED", "TARGET_MISMATCH")

    def test_push_instead_of_rewrite(self):
        self.git("config", "url.https://other.example/.pushInsteadOf", "https://github.com/")
        self.run_check("BLOCKED", "FETCH_PUSH_MISMATCH")

    def test_safe_rewrite(self):
        self.git("remote", "set-url", "origin", "approved:owner/repo")
        self.git("config", "url.https://github.com/.insteadOf", "approved:")
        self.run_check()

    def test_credentials_redacted(self):
        marker = "SYNTHETIC-DO-NOT-DISCLOSE"
        for url in (f"https://{marker}@github.com/owner/repo",
                    f"https://user:{marker}@github.com/owner/repo",
                    f"ssh://git:{marker}@github.com/owner/repo"):
            with self.subTest(scheme=url.split(":")[0]):
                self.git("remote", "set-url", "origin", url)
                result = self.run_check("BLOCKED", "EMBEDDED_CREDENTIALS")
                self.assertNotIn(marker, result.stdout + result.stderr)

    def test_unsupported_urls(self):
        for url in ("file:///tmp/repo", "http://github.com/owner/repo", "ext::anything",
                    "https://github.com/owner/repo?", "https://github.com/owner/repo#",
                    "https://github.com/own\rer/repo", "https://github.com/owner/repo\n",
                    "https://github.com/owner/%72epo", "https://github.com:443/owner/repo",
                    "https://github.com:/owner/repo", "ssh://git@github.com:/owner/repo",
                    "ssh://git@github.com:22/owner/repo", "git@github-alias:owner/repo"):
            with self.subTest(url=url):
                self.git("remote", "set-url", "origin", url)
                self.run_check("BLOCKED")

    def test_credentials_cannot_be_hidden_by_rewrite(self):
        marker = "SYNTHETIC-HIDDEN-CREDENTIAL"
        self.git("remote", "set-url", "origin", f"https://{marker}@github.com/owner/repo")
        self.git("config", "url.https://github.com/.insteadOf", f"https://{marker}@github.com/")
        result = self.run_check("BLOCKED", "EMBEDDED_CREDENTIALS")
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_environment_override(self):
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                     "GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"):
            with self.subTest(name=name):
                self.env[name] = "synthetic-override"
                self.run_check("BLOCKED", "GIT_ENV_OVERRIDE")
                del self.env[name]

    def test_invalid_arguments_are_redacted(self):
        result = self.run_check("BLOCKED", "INVALID_ARGUMENTS", transport="SYNTHETIC-SECRET")
        self.assertNotIn("SYNTHETIC-SECRET", result.stdout)
        self.run_check("BLOCKED", "INVALID_ARGUMENTS", remote="--help")

    def test_git_error_is_redacted(self):
        # Git emits the invalid boolean value to stderr; helper must not forward it.
        marker = "SYNTHETIC-PRIVATE-ERROR"
        self.git("config", "remote.origin.mirror", marker)
        result = self.run_check("BLOCKED", "GIT_CHECK_FAILED")
        self.assertNotIn(marker, result.stdout + result.stderr)

    def test_no_mutations(self):
        (self.root / "tracked.txt").write_text("one\n")
        self.git("add", "--", "tracked.txt")
        self.git("commit", "-m", "fixture")
        (self.root / "tracked.txt").write_text("two\n")
        self.git("add", "--", "tracked.txt")
        (self.root / "untracked.txt").write_text("keep\n")

        def snapshot():
            return {str(p.relative_to(self.root)): p.read_bytes()
                    for p in self.root.rglob("*") if p.is_file()}

        before = snapshot()
        self.run_check()
        self.run_check("BLOCKED", host="other.example")
        self.assertEqual(before, snapshot())

    def test_standalone_copy(self):
        copied = self.base / "copied-skill"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
        self.run_check(script=copied / "scripts" / "check_target.py")

    def test_standalone_document_links(self):
        copied = self.base / "docs-copy"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
        links = 0
        for document in copied.rglob("*.md"):
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                self.assertNotIn("://", target, "Keep this offline link test local-only")
                resolved = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.is_relative_to(copied.resolve()))
                self.assertTrue(resolved.exists(), f"Broken link in {document.name}: {target}")
                links += 1
        self.assertGreater(links, 0)
        self.assertFalse(list(copied.rglob("*:Zone.Identifier")))

    def test_timeout_and_exception_redaction(self):
        for error, reason in ((subprocess.TimeoutExpired("SYNTHETIC-SECRET", 10), "GIT_TIMEOUT"),
                              (OSError("SYNTHETIC-SECRET"), "CHECK_UNAVAILABLE")):
            with self.subTest(reason=reason), patch.dict(os.environ, self.env, clear=True):
                output = io.StringIO()
                with patch.object(helper.subprocess, "run", side_effect=error), contextlib.redirect_stdout(output):
                    self.assertEqual(helper.main(self.args()), 2)
                self.assertEqual(json.loads(output.getvalue()), {"status": "BLOCKED", "reason": reason})

    def test_subprocess_is_read_only_and_shell_free(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"fixture\n", stderr=b"")
        with patch.object(helper.subprocess, "run", return_value=completed) as run:
            self.assertEqual(helper.git(self.root, "rev-parse", "--show-toplevel"), "fixture\n")
        call = run.call_args
        self.assertEqual(call.args[0], ["git", "--no-optional-locks", "-C", str(self.root),
                                       "rev-parse", "--show-toplevel"])
        self.assertFalse(call.kwargs.get("shell", False))
        self.assertEqual(call.kwargs["timeout"], 10)
        self.assertEqual(call.kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(call.kwargs["stdout"], subprocess.PIPE)

    def test_fixed_sha_push_recipe_offline(self):
        # Exercise only the documented Git command mechanics, not the helper's
        # target policy or authenticated GitHub workflow. Remote is a local fixture.
        bare = self.base / "remote.git"
        self.git("init", "--bare", str(bare))
        self.git("remote", "add", "fixture", str(bare))
        self.git("config", "push.followTags", "true")
        self.git("config", "remote.fixture.push", "refs/heads/main:refs/heads/unwanted")
        self.git("commit", "--allow-empty", "-m", "reviewed")
        reviewed = self.git("rev-parse", "HEAD").decode().strip()
        self.git("tag", "-a", "not-requested", "-m", "fixture")
        self.git("commit", "--allow-empty", "-m", "later-unreviewed")
        self.git("push", "--porcelain", "--no-follow-tags", "--recurse-submodules=no",
                 "fixture", f"{reviewed}:refs/heads/topic")
        refs = self.git("ls-remote", "--quiet", "fixture").decode().splitlines()
        self.assertEqual(refs, [f"{reviewed}\trefs/heads/topic"])
        upstream = subprocess.run(["git", "-C", str(self.root), "config", "--get",
                                   "branch.main.remote"], env=self.env, capture_output=True, timeout=10)
        self.assertEqual(upstream.returncode, 1)


if __name__ == "__main__":
    unittest.main()
