from __future__ import annotations

import base64
import contextlib
import io
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import test_scan_sensitive as baseline_tests

inert_samples = baseline_tests.inert_samples

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scan_sensitive as scanner


class ExpandedTests(unittest.TestCase):
    def setUp(self):
        scanner._total = scanner._items = 0

    def test_json_export_inline_assignments(self):
        for value in (b'{"password": "' + b"a" * 12 + b'"}',
                      b"export CLIENT_SECRET=" + b"a" * 12,
                      b'{"aws_secret_access_key":"' + b"a" * 40 + b'"}'):
            with self.subTest(kind=value[:8]):
                self.assertTrue(scanner.scan("fixture.txt", value))

    def test_url_and_basic_credentials(self):
        for value, rule in (
            (b"postgresql://" + b"user:p%40ss@db.invalid/name", "credential-url"),
            (b"Authorization: Basic " + base64.b64encode(b"user:pass"), "basic-auth"),
        ):
            with self.subTest(rule=rule):
                self.assertIn((rule, "fixture.txt"), scanner.scan("fixture.txt", value))

    def test_public_values_and_references_remain_clean(self):
        for value in (
            b"https://user@host.invalid/name", b"https://user:@host.invalid",
            b"https://user:${PASSWORD}@host.invalid", b"password=${PASSWORD}",
            b'"password": ""', b"password=short", b"MY_PASSWORD_DOC=" + b"a" * 32,
            b"Authorization: Basic !!!", b"Authorization: Basic " + base64.b64encode(b"username"),
            b"pk_" + b"live_" + b"a" * 32,
            b"sb_" + b"publishable_" + b"a" * 32,
            b"client_id=" + b"a" * 32,
        ):
            self.assertEqual(scanner.scan("fixture.txt", value), [])

    def test_basic_is_redacted(self):
        raw = b"synthetic-user:synthetic-pass"
        encoded = base64.b64encode(raw)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = scanner.report(scanner.scan("fixture.txt", b"Authorization: Basic " + encoded))
        self.assertEqual(status, 1)
        for value in (raw, encoded, b"fixture.txt"):
            self.assertNotIn(value.decode(), output.getvalue())

    def test_all_new_prefix_rules_boundaries_and_redaction(self):
        old = {"private-key", "github-token", "github-fine-grained-pat", "aws-access-key",
               "aws-secret-access-key", "google-api-key", "jwt", "bearer-token",
               "slack-webhook", "npmrc-auth-token", "pypi-api-token", "credential-assignment"}
        for rule, sample in inert_samples().items():
            if rule in old:
                continue
            with self.subTest(rule=rule):
                self.assertNotIn(rule, scanner.matching_rules(sample[:-1]))
                self.assertNotIn(rule, scanner.matching_rules(sample[:-1] + b"!"))
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(scanner.report(scanner.scan("fixture.txt", sample)), 1)
                self.assertNotIn(sample.decode(), output.getvalue())
                self.assertNotIn("fixture.txt", output.getvalue())

    def test_all_explicit_service_keys(self):
        values = {
            "ai-key-assignment": b"a" * 20,
            "cloudflare-credential": b"a" * 40,
            "azure-credential": b"a" * 32,
            "azure-sas": b"sv=2026&sig=" + b"a" * 32,
            "netlify-token": b"a" * 40,
            "vercel-token-assignment": b"a" * 24,
            "supabase-service-role": b"a" * 20,
            "discord-token": b"a" * 32,
            "notion-token-assignment": b"secret" + b"_" + b"a" * 32,
            "atlassian-token-assignment": b"a" * 24,
            "datadog-api-key": b"a" * 32,
            "datadog-app-key": b"a" * 40,
            "grafana-token-assignment": b"a" * 32,
            "vault-token-assignment": b"s." + b"a" * 24,
        }
        self.assertEqual(set(values), set(scanner.CONTEXT_RULES))
        for rule, (keys, _) in scanner.CONTEXT_RULES.items():
            for key in keys.split():
                with self.subTest(rule=rule, key=key):
                    value = values[rule]
                    sample = b'{"' + key.upper().encode() + b'": "' + value + b'"}'
                    self.assertIn(rule, scanner.matching_rules(sample))
                    for negative in (b'"' + key.encode() + b'": "short"',
                                     key.encode() + b"=${LONG_VARIABLE_REFERENCE}",
                                     b"documentation=" + value,
                                     b"example_" + key.encode() + b"=" + value):
                        self.assertNotIn(rule, scanner.matching_rules(negative))
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(scanner.report(scanner.scan("fixture.txt", sample)), 1)
                    self.assertNotIn(value.decode(), output.getvalue())

    def test_url_variants(self):
        for scheme in (b"http", b"https", b"postgres", b"postgresql", b"mysql",
                       b"mongodb", b"mongodb+srv", b"redis", b"rediss"):
            self.assertIn("credential-url", scanner.matching_rules(scheme + b"://user:p%40ss@host.invalid"))
        for value in (b"ssh://user@host.invalid", b"https://host.invalid/user:pass",
                      b"https://user:%24%7BPASSWORD%7D@host.invalid"):
            self.assertNotIn("credential-url", scanner.matching_rules(value))

    def test_basic_header_shapes_and_limits(self):
        for prefix in (b"Authorization: Basic ", b'"Authorization": "Basic ',
                       b"proxy-authorization = 'basic "):
            self.assertIn("basic-auth", scanner.matching_rules(prefix + base64.b64encode(b"user:pass") + b'"'))
        for value in (b"user:", b"user", b"user:${PASSWORD}"):
            self.assertNotIn("basic-auth", scanner.matching_rules(b"Authorization: Basic " + base64.b64encode(value)))
        self.assertNotIn("basic-auth", scanner.matching_rules(b"Authorization: Basic " + base64.b64encode(b"u:p") + b"!"))
        at_limit = base64.b64encode(b"u:" + b"a" * 3070)
        self.assertEqual(len(at_limit), 4096)
        self.assertIn("basic-auth", scanner.matching_rules(b"Authorization: Basic " + at_limit))
        for length in (4097, 10000):
            with self.assertRaises(scanner.ScanError):
                scanner.matching_rules(b"Authorization: Basic " + b"a" * length)
        with self.assertRaises(scanner.ScanError):
            scanner.matching_rules(b"https://u:" + b"a" * 4096 + b"@host.invalid")
        authority = b"u:" + b"a" * 4081 + b"@host.invalid"
        self.assertEqual(len(authority), 4096)
        self.assertIn("credential-url", scanner.matching_rules(b"https://" + authority))
        with self.assertRaises(scanner.ScanError):
            scanner.matching_rules(b"https://" + b"u" + authority)

    def test_label_scanning_uses_new_rules(self):
        sample = b"npm" + b"_" + b"a" * 36
        label = sample.decode() + ".txt"
        self.assertIn(("npm-token", label), scanner.scan(label, b"safe"))

    def test_variants_and_public_keys(self):
        variants = {
            "gitlab-token": [prefix + b"a" * 20 for prefix in (b"glpat-", b"gldt-", b"glrt-", b"glrtr-")],
            "vercel-token": [b"vc" + prefix + b"_" + b"a" * 24 for prefix in (b"p", b"i", b"a", b"r", b"k")],
            "stripe-secret": [b"rk_" + b"test_" + b"a" * 32, b"whsec" + b"_" + b"a" * 20],
            "vault-token": [b"hvb" + b"." + b"a" * 150],
            "slack-token": [b"xoxp-" + b"1" * 20, b"xapp-" + b"1-AAAA-1234-abcdef"],
            "grafana-token": [b"glc" + b"_" + b"a" * 32],
        }
        for rule, samples in variants.items():
            for sample in samples:
                self.assertIn(rule, scanner.matching_rules(sample))
        for sample in (b"publishable_key=pk_" + b"live_" + b"a" * 32,
                       b"SUPABASE_PUBLISHABLE_KEY=sb_" + b"publishable_" + b"a" * 32,
                       b"DISCORD_CLIENT_ID=" + b"1" * 19,
                       b"AZURE_TENANT_ID=" + b"a" * 32,
                       b"DATADOG_API_KEY=" + b"g" * 32):
            self.assertEqual(scanner.matching_rules(sample), set())


class ExpandedHookTests(unittest.TestCase):
    git = baseline_tests.GitModeTests.git
    repository = baseline_tests.GitModeTests.repository
    run_scanner = baseline_tests.GitModeTests.run_scanner

    def test_real_hooks_index_message_and_removed_history(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = self.repository(Path(raw))
            manager = Path(scanner.__file__).with_name("manage_hooks.py")
            installed = subprocess.run([sys.executable, "-B", str(manager), "install",
                                        "--repo", str(repo), "--engine", "python"],
                                       capture_output=True)
            self.assertEqual(installed.returncode, 0, installed.stdout)
            source = repo / "fixture.txt"
            source.write_text("safe")
            self.git(repo, "add", "fixture.txt")
            self.git(repo, "commit", "-q", "-m", "baseline")
            remote = Path(raw) / "remote.git"
            self.git(Path(raw), "init", "--bare", "-q", str(remote))
            self.git(repo, "push", str(remote), "HEAD:refs/heads/main")

            url = b"postgresql://" + b"user:synthetic-pass@host.invalid/db"
            source.write_bytes(url)
            self.git(repo, "add", "fixture.txt")
            source.write_text("worktree correction is not staged")
            rejected = subprocess.run(["git", "commit", "-qm", "blocked"], cwd=repo, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"credential-url", rejected.stdout + rejected.stderr)
            self.assertNotIn(url, rejected.stdout + rejected.stderr)

            self.git(repo, "add", "fixture.txt")
            message = b"Authorization: Basic " + base64.b64encode(b"user:synthetic-pass")
            rejected = subprocess.run(["git", "commit", "-q", "-m", message.decode()], cwd=repo, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"basic-auth", rejected.stdout + rejected.stderr)
            self.assertNotIn(message, rejected.stdout + rejected.stderr)
            self.git(repo, "commit", "-qm", "safe correction")

            # Deliberately construct otherwise-unreachable history in this fixture.
            value = inert_samples()["npm-token"]
            source.write_bytes(value)
            self.git(repo, "add", "fixture.txt")
            self.git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture history")
            source.write_text("removed")
            self.git(repo, "add", "fixture.txt")
            self.git(repo, "commit", "-qm", "remove fixture")
            rejected = subprocess.run(["git", "push", str(remote), "HEAD:refs/heads/main"], cwd=repo, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"npm-token", rejected.stdout + rejected.stderr)
            self.assertNotIn(value, rejected.stdout + rejected.stderr)
            head = self.git(repo, "rev-parse", "HEAD")
            ref = "refs/heads/" + value.decode()
            rejected_ref = self.run_scanner(repo, "--pre-push", input_text=f"HEAD {head} {ref} {'0' * 40}\n")
            self.assertEqual(rejected_ref.returncode, 1)
            self.assertNotIn(value.decode(), rejected_ref.stdout + rejected_ref.stderr)


if __name__ == "__main__":
    unittest.main()
