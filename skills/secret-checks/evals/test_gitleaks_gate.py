"""Real Git hooks + pinned Gitleaks; no network or changes to the checkout's Git config."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import manage_hooks
SPEC = importlib.util.spec_from_file_location('gate', ROOT / 'scripts/gitleaks_gate.py')
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
# An invalid, non-issued key marker assembled only inside isolated tests.
CANARY = (b'-----BEGIN ' + b'PRIVATE KEY-----\n' + b'!invalid!' * 10 +
          b'\n-----END ' + b'PRIVATE KEY-----\n')


class GitGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='source002-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'trusted bundle'
        runner = os.environ.get('SECRET_CHECKS_RUNNER')
        if not runner:
            self.skipTest('Set SECRET_CHECKS_RUNNER to the verified batch runner')
        for name, (data, mode) in manage_hooks.source_payload('gitleaks', runner=runner).items():
            target = self.bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        receiver = (self.bundle / 'hooks/pre-push').read_text().replace(' pre-push ', ' pre-receive ')
        (self.bundle / 'hooks/pre-receive').write_text(receiver)
        (self.bundle / 'hooks/pre-receive').chmod(0o700)
        self.repo = self.root / 'work'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'GITLEAKS_'))}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_AUTHOR_NAME='Example', GIT_AUTHOR_EMAIL='example@example.invalid',
                        GIT_COMMITTER_NAME='Example', GIT_COMMITTER_EMAIL='example@example.invalid')
        self.git('init', '-q', '-b', 'main', str(self.repo), cwd=self.root)
        self.git('config', 'core.hooksPath', str(self.bundle / 'hooks'))

    def git(self, *args, cwd=None, ok=True):
        result = subprocess.run(['/usr/bin/git', *args], cwd=cwd or self.repo, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, 'Git operation failed; payload suppressed')
        return result

    def write(self, name, data):
        (self.repo / name).write_bytes(data)
        self.git('add', '--', name)

    def commit(self, message='ordinary change', bypass=False, ok=True):
        args = ['-c', 'core.hooksPath=/dev/null'] if bypass else []
        return self.git(*args, 'commit', '-qm', message, ok=ok)

    def rejected(self, result, marker=b'REJECTED'):
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn(marker, output)
        self.assertNotIn(CANARY.splitlines()[0], output)

    def remote(self):
        remote = self.root / 'receive.git'
        self.git('init', '--bare', '-q', str(remote), cwd=self.root)
        self.git('--git-dir=' + str(remote), 'config', 'core.hooksPath', str(self.bundle / 'hooks'))
        return str(remote)

    def hook(self, name, data=b''):
        return subprocess.run([str(self.bundle / 'hooks' / name)], cwd=self.repo,
                              env=self.env, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30)

    def test_safe_commit_and_push(self):
        self.write('readme.txt', b'ordinary text\n')
        self.commit()
        remote = self.remote()
        self.git('push', remote, 'HEAD:refs/heads/main')
        self.assertEqual(self.git('--git-dir=' + remote, 'rev-parse', 'refs/heads/main').stdout,
                         self.git('rev-parse', 'HEAD').stdout)

    def test_staged_secret_even_when_worktree_is_clean(self):
        self.write('config.txt', CANARY)
        (self.repo / 'config.txt').write_bytes(b'clean now\n')
        self.rejected(self.commit(ok=False))

    def test_lfs_header_in_source_does_not_block_or_exempt_commit(self):
        source = b'header = "version https://git-lfs.github.com/spec/v1"\n'
        self.write('example.py', source)
        self.commit()
        self.write('example.py', source + CANARY)
        self.rejected(self.commit(ok=False))

    def test_unstaged_secret_does_not_change_index_scan(self):
        self.write('config.txt', b'clean staged content\n')
        (self.repo / 'config.txt').write_bytes(CANARY)
        self.commit()

    def test_message_secret(self):
        self.write('readme', b'ok\n')
        self.rejected(self.commit(CANARY.decode(), ok=False))

    def test_deleted_secret_in_history_blocked_before_push(self):
        self.write('config', CANARY)
        self.commit(bypass=True)
        self.write('config', b'clean now\n')
        self.commit()
        self.rejected(self.git('push', self.remote(), 'HEAD:refs/heads/new', ok=False))

    def test_receiver_blocks_bypass_and_keeps_ref_absent(self):
        self.write('config', CANARY)
        self.commit(bypass=True)
        self.write('config', b'clean now\n')
        self.commit()
        remote = self.remote()
        self.rejected(self.git('push', '--no-verify', remote, 'HEAD:refs/heads/main', ok=False))
        self.assertNotEqual(self.git('--git-dir=' + remote, 'show-ref', '--verify',
                                    'refs/heads/main', ok=False).returncode, 0)

    def test_candidate_cannot_weaken_receiver_policy(self):
        self.write('.gitleaks.toml', b'title="disable"\n')
        self.write('.gitleaksignore', b'*\n')
        self.write('config', CANARY + b'# gitleaks:allow\n')
        self.commit(bypass=True)
        self.rejected(self.git('push', '--no-verify', self.remote(), 'HEAD:refs/heads/main', ok=False))

    def test_annotated_tag_message_and_direct_blob_tag(self):
        self.write('readme', b'ok\n')
        self.commit()
        self.git('tag', '-a', 'release', '-m', CANARY.decode())
        self.rejected(self.git('push', '--no-verify', self.remote(), 'refs/tags/release', ok=False))
        self.write('payload', CANARY)
        identity = self.git('rev-parse', ':payload').stdout.strip().decode()
        self.git('update-ref', 'refs/tags/blob', identity)
        self.rejected(self.git('push', '--no-verify', self.remote(), 'refs/tags/blob', ok=False))

    def test_multiple_refs_rejects_entire_receive(self):
        self.write('readme', b'ok\n')
        self.commit()
        self.git('branch', 'safe')
        self.write('payload', CANARY)
        self.commit(bypass=True)
        remote = self.remote()
        self.rejected(self.git('push', '--no-verify', remote, 'safe:refs/heads/safe',
                               'main:refs/heads/bad', ok=False))
        self.assertEqual(self.git('--git-dir=' + remote, 'for-each-ref').stdout, b'')

    def test_force_push_with_secret_rejected(self):
        self.write('readme', b'ok\n')
        self.commit()
        remote = self.remote()
        self.git('push', remote, 'HEAD:refs/heads/main')
        old = self.git('rev-parse', 'HEAD').stdout
        self.write('payload', CANARY)
        self.commit(bypass=True)
        self.rejected(self.git('push', '--no-verify', '--force', remote, 'HEAD:refs/heads/main', ok=False))
        self.assertEqual(self.git('--git-dir=' + remote, 'rev-parse', 'refs/heads/main').stdout, old)

    def test_merge_resolution_content_rejected(self):
        self.write('readme', b'ok\n')
        self.commit()
        self.git('branch', 'side')
        self.write('main', b'ok\n')
        self.commit()
        first = self.git('rev-parse', 'HEAD').stdout.strip().decode()
        self.git('checkout', '-q', 'side')
        self.write('side', b'ok\n')
        self.commit()
        second = self.git('rev-parse', 'HEAD').stdout.strip().decode()
        self.write('merge-only', CANARY)
        tree = self.git('write-tree').stdout.strip().decode()
        merged = self.git('commit-tree', tree, '-p', first, '-p', second, '-m', 'merge').stdout.strip().decode()
        self.git('update-ref', 'refs/heads/merged', merged)
        self.rejected(self.git('push', '--no-verify', self.remote(), 'merged:refs/heads/merged', ok=False))

    def test_unsupported_inputs_and_size(self):
        for name, content in [('binary', b'\0payload'), ('encoding', b'\xff'),
                              ('archive.zip', b'not actually a zip'),
                              ('large', b'x' * (gate.MAX_BYTES + 1)),
                              ('lfs', b'version https://git-lfs.github.com/spec/v1\n')]:
            with self.subTest(name=name):
                self.write(name, content)
                self.rejected(self.hook('pre-commit'), b'INCOMPLETE')
                self.git('rm', '--cached', '-q', name)

    def test_symlink_rejected(self):
        (self.repo / 'link').symlink_to('/does-not-exist')
        self.git('add', 'link')
        result = self.hook('pre-commit')
        self.assertEqual(result.returncode, 2)
        self.rejected(result, b'ERROR policy unsupported-index')

    def test_path_value_is_not_printed(self):
        name = CANARY.decode().replace('\n', '_')
        self.write(name, b'ordinary text\n')
        self.rejected(self.hook('pre-commit'))

    def test_text_with_binary_magic_is_still_scanned(self):
        self.write('renamed.txt', b'%PDF-1.7\n' + CANARY)
        self.rejected(self.hook('pre-commit'))

    def test_submodule_is_incomplete(self):
        self.write('readme', b'ok\n')
        self.commit()
        identity = self.git('rev-parse', 'HEAD').stdout.strip().decode()
        self.git('update-index', '--add', '--cacheinfo', '160000,' + identity + ',module')
        result = self.hook('pre-commit')
        self.assertEqual(result.returncode, 2)
        self.rejected(result, b'ERROR policy unsupported-index')

    def test_scanner_missing_or_modified(self):
        self.write('readme', b'ok\n')
        binary = self.bundle / 'bin/gitleaks-runner'
        binary.rename(self.bundle / 'bin/saved')
        self.rejected(self.hook('pre-commit'), b'ERROR')
        binary.write_bytes(b'not the reviewed binary')
        self.rejected(self.hook('pre-commit'), b'ERROR')

    def test_invalid_config_fails_without_echoing_content(self):
        self.write('readme', b'ok\n')
        (self.bundle / 'gitleaks.toml').write_bytes(CANARY)
        self.rejected(self.hook('pre-commit'), b'ERROR')

    def test_malformed_input_and_missing_object(self):
        self.rejected(self.hook('pre-push', CANARY), b'ERROR')
        self.rejected(self.hook('pre-push', b'refs/heads/main ' + b'1'*40 +
                                b' refs/heads/main ' + b'0'*40 + b'\n'), b'ERROR')

    def test_shallow_history_is_incomplete(self):
        self.write('readme', b'ok\n')
        self.commit()
        self.write('other', b'ok\n')
        self.commit()
        clone = self.root / 'shallow'
        self.git('clone', '-q', '--depth=1', self.repo.as_uri(), str(clone), cwd=self.root)
        self.repo = clone
        self.rejected(self.hook('pre-commit'), b'INCOMPLETE')

    def test_deletion_does_not_hide_another_ref(self):
        self.write('payload', CANARY)
        self.commit(bypass=True)
        identity = self.git('rev-parse', 'HEAD').stdout.strip()
        raw = (b'(delete) ' + b'0'*40 + b' refs/heads/old ' + identity + b'\n' +
               b'refs/heads/main ' + identity + b' refs/heads/new ' + b'0'*40 + b'\n')
        self.rejected(self.hook('pre-push', raw))


class ScannerFailureTests(unittest.TestCase):
    def scanner(self):
        scanner = gate.Scanner.__new__(gate.Scanner)
        scanner.binary = Path('/unused')
        scanner.docker = None
        scanner.total = 0
        scanner.inputs = []
        scanner.deadline = time.monotonic() + 120
        return scanner

    def test_unknown_exit_empty_and_invalid_reports(self):
        for status, output in [(0, b''), (0, b'null'), (0, b'[{}]'), (10, b'[]'),
                               (1, b'[]'), (42, b'[]'), (0, CANARY)]:
            with self.subTest(status=status, output_length=len(output)):
                result = subprocess.CompletedProcess([], status, output, CANARY)
                with patch.object(gate, 'run', return_value=result):
                    with self.assertRaises(gate.Rejected) as caught:
                        scanner = self.scanner()
                        scanner.scan(b'normal', 'test')
                        scanner.finish()
                    self.assertEqual(caught.exception.code, 2)
                    self.assertNotIn(CANARY.decode(), caught.exception.reason)

    def test_timeout_is_not_clean(self):
        with patch.object(gate.subprocess, 'run', side_effect=subprocess.TimeoutExpired('scanner', 15)):
            with self.assertRaises(gate.Rejected) as caught:
                scanner = self.scanner()
                scanner.scan(b'normal', 'test')
                scanner.finish()
            self.assertEqual(caught.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
