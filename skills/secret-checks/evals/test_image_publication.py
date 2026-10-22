"""Synthetic, local-only regression fixtures; never read personal images."""
import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import publication_policy as policy


def decoders_available():
    try:
        from importlib.metadata import version
        return (version('Pillow') == '12.3.0' and version('pillow-heif') == '1.8.1'
                and version('defusedxml') == '0.7.1')
    except Exception:
        return False


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\0\0\0')) + chunk(b'IEND', b''))


class PublicationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='publication-test-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '-q', '-b', 'main')

    def git(self, *args):
        result = subprocess.run(['/usr/bin/git', *args], cwd=self.repo, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        self.assertEqual(result.returncode, 0, 'fixture Git command failed')
        return result.stdout.strip()

    def scan(self, *args, data=None):
        return subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/scan_sensitive.py'), *args],
                              cwd=self.repo, env=self.env, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=30)

    def test_valid_static_png_is_allowed_and_reported(self):
        if not decoders_available():
            self.skipTest('Pinned image decoder environment required')
        (self.repo / 'diagram.png').write_bytes(png())
        self.git('add', '--', 'diagram.png')
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'images_allowed:1', result.stdout)

    def test_101_changed_paths_refuse_even_when_blob_is_shared(self):
        for n in range(101):
            path = f'file-{n}.txt'
            (self.repo / path).write_bytes(b'ordinary\n')
            self.git('add', '--', path)
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'commit-files', result.stderr)

    def test_100_changed_paths_pass_and_unchanged_paths_do_not_count(self):
        for start, end in ((0, 100), (100, 200)):
            for n in range(start, end):
                path = f'file-{n}.txt'
                (self.repo / path).write_bytes(b'ordinary\n')
                self.git('add', '--', path)
            self.assertEqual(self.scan('--staged').returncode, 0)
            self.git('commit', '-qm', 'fixture')
        self.assertEqual(self.scan('--staged').returncode, 0)

    def test_image_allowance_does_not_allow_secret_text_or_message(self):
        if not decoders_available():
            self.skipTest('Pinned image decoder environment required')
        (self.repo / 'diagram.png').write_bytes(png())
        canary = b'-----BEGIN ' + b'PRIVATE KEY-----'
        (self.repo / 'note.txt').write_bytes(canary)
        self.git('add', '--', 'diagram.png', 'note.txt')
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(canary, result.stdout + result.stderr)
        result = self.scan('--file', str(self.repo / 'diagram.png'), '--label', 'message.png')
        self.assertEqual(result.returncode, 2, 'A message must not gain the image exemption')

    def test_svg_is_still_secret_scanned(self):
        if not decoders_available():
            self.skipTest('Pinned image decoder environment required')
        canary = b'-----BEGIN ' + b'PRIVATE KEY-----'
        (self.repo / 'diagram.svg').write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><text>'
            + canary + b'</text></svg>')
        self.git('add', '--', 'diagram.svg')
        self.assertEqual(self.scan('--staged').returncode, 1)

    def policy_git(self, *args, data=None):
        r = subprocess.run(['/usr/bin/git', '--no-replace-objects', *args], cwd=self.repo,
                           env=self.env, input=data, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=15)
        if r.returncode:
            raise policy.PolicyError('git-incomplete')
        return r.stdout

    def commit_content(self, content):
        (self.repo / 'record.txt').write_bytes(content)
        self.git('add', '--', 'record.txt')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def updates(self, old, new, ref=b'main'):
        return b'refs/heads/' + ref + b' ' + new + b' refs/heads/' + ref + b' ' + old + b'\n'

    def test_push_counts_intermediate_deleted_content_and_unions_refs(self):
        old = self.commit_content(b'baseline')
        middle = self.commit_content(b'x' * 100)
        new = self.commit_content(b'final')
        raw = self.updates(old, new) + self.updates(old, middle, b'other')
        with patch.object(policy, 'git', self.policy_git):
            self.assertEqual(policy.check_updates(raw), (2, 105))
            with patch.object(policy, 'PUSH_BYTES', 104):
                with self.assertRaisesRegex(policy.PolicyError, 'push-bytes'):
                    policy.check_updates(raw)
            # A new branch does not trust other refs as prior publication evidence.
            self.assertEqual(policy.check_updates(self.updates(b'0' * 40, new)), (3, 113))
            self.assertEqual(policy.check_updates(self.updates(new, b'0' * 40)), (0, 0))

    def test_push_force_update_and_missing_baseline(self):
        old = self.commit_content(b'old')
        self.git('checkout', '--orphan', 'replacement')
        new = self.commit_content(b'new')
        with patch.object(policy, 'git', self.policy_git):
            self.assertEqual(policy.check_updates(self.updates(old, new)), (1, 3))
            with self.assertRaises(policy.PolicyError):
                policy.check_updates(self.updates(b'a' * 40, new))


class BudgetTests(unittest.TestCase):
    def test_boundaries(self):
        for push, count, size in ((False, 100, 20 * 1024 * 1024), (True, 500, 50 * 1024 * 1024)):
            policy.enforce(count, size, push=push)
            for n, b in ((count + 1, size), (count, size + 1)):
                with self.assertRaises(policy.PolicyError):
                    policy.enforce(n, b, push=push)

    def test_malformed_updates_and_unknown_child_output_are_fixed_errors(self):
        for raw in (b'x' * 65537, b'not an update\n'):
            with self.assertRaises(policy.PolicyError):
                policy.check_updates(raw)
        fake = subprocess.CompletedProcess([], 99, b'private diagnostic', b'')
        with patch.object(policy.subprocess, 'run', return_value=fake):
            with self.assertRaisesRegex(policy.PolicyError, '^image-validation-incomplete$'):
                policy.Images().validate('diagram.png', png())
        with patch.object(policy.subprocess, 'run', side_effect=subprocess.TimeoutExpired('worker', 10)):
            with self.assertRaisesRegex(policy.PolicyError, 'image-validation-unavailable-or-timeout'):
                policy.Images().validate('diagram.png', png())


@unittest.skipUnless(decoders_available(), 'Pinned image decoder environment required')
class ImageValidationTests(unittest.TestCase):
    def raster(self, kind, multiple=False):
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
        first = Image.new('RGB', (2, 2), 'black')
        buffer = io.BytesIO()
        options = {'save_all': True, 'append_images': [Image.new('RGB', (2, 2), 'white')]} if multiple else {}
        first.save(buffer, format=kind, **options)
        return buffer.getvalue()

    def test_all_static_formats_decode_and_cache(self):
        for extension, kind in policy.FORMATS.items():
            if kind == 'SVG':
                continue
            with self.subTest(kind=kind, extension=extension):
                images = policy.Images()
                data = self.raster(kind)
                self.assertTrue(images.validate('diagram' + extension, data))
                self.assertTrue(images.validate('copy' + extension, data))
                self.assertEqual(images.allowed, 1)

    def test_wrong_format_and_corrupt_input_refuse(self):
        for name, data in (('wrong.jpg', png()), ('broken.png', png()[:30]),
                           ('fake.gif', b'ordinary text'), ('empty.tiff', b''),
                           ('broken.heic', b'not HEIC')):
            with self.subTest(name=name), self.assertRaises(policy.PolicyError):
                policy.Images().validate(name, data)

    def test_multiframe_and_multipage_refuse(self):
        for extension, kind in (('.gif', 'GIF'), ('.tiff', 'TIFF'), ('.webp', 'WEBP'),
                                ('.png', 'PNG'), ('.heic', 'HEIF')):
            with self.subTest(kind=kind), self.assertRaisesRegex(policy.PolicyError, 'image-not-static'):
                policy.Images().validate('sequence' + extension, self.raster(kind, multiple=True))

    def test_size_dimensions_and_missing_decoder_refuse(self):
        with self.assertRaisesRegex(policy.PolicyError, 'image-bytes-limit'):
            policy.Images().validate('large.png', b'x' * (policy.IMAGE_BYTES + 1))
        data = bytearray(png())
        data[16:24] = struct.pack('>II', 20001, 1000)
        data[29:33] = struct.pack('>I', zlib.crc32(data[12:29]))
        with self.assertRaisesRegex(policy.PolicyError, 'image-dimensions'):
            policy.Images().validate('huge.png', bytes(data))
        fake = subprocess.CompletedProcess([], 3, b'', b'')
        with patch.object(policy.subprocess, 'run', return_value=fake):
            with self.assertRaisesRegex(policy.PolicyError, 'image-decoder-unavailable'):
                policy.Images().validate('image.png', png())

    def test_svg_restricted_subset_and_active_content(self):
        prefix = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        self.assertFalse(policy.Images().validate('diagram.svg', prefix + b'<rect width="2" height="2"/></svg>'))
        for element in (b'<script/>', b'<foreignObject/>', b'<animate/>',
                        b'<image href="data:image/png;base64,AA=="/>',
                        b'<use href="https://example.invalid/image"/>',
                        b'<rect onclick="run()"/>', b'<style>@import "x";</style>'):
            with self.subTest(element=element), self.assertRaises(policy.PolicyError):
                policy.Images().validate('active.svg', prefix + element + b'</svg>')
        for data in (b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///not-readable">]>' + prefix + b'&x;</svg>',
                     b'<?xml-stylesheet href="https://example.invalid/style"?>' + prefix + b'</svg>',
                     prefix + b'<g>' * 65 + b'</g>' * 65 + b'</svg>'):
            with self.assertRaises(policy.PolicyError):
                policy.Images().validate('unsafe.svg', data)


@unittest.skipUnless(decoders_available() and os.environ.get('SECRET_CHECKS_RUNNER'),
                     'Pinned image environment and runner required')
class RealImageHookTests(unittest.TestCase):
    def test_combined_images_commit_push_and_refusal(self):
        import test_gitleaks_gate as existing
        fixture = existing.GitGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        runtime = 'docker' if os.environ.get('SECRET_CHECKS_DOCKER') == '1' else 'native'
        payload = existing.manage_hooks.source_payload('combined', runtime=runtime,
                                                       runner=os.environ['SECRET_CHECKS_RUNNER'],
                                                       commit_gitleaks=True)
        for name, (data, mode) in payload.items():
            target = fixture.bundle / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        generator = ImageValidationTests()
        for suffix, kind in (('.png', 'PNG'), ('.jpg', 'JPEG'), ('.webp', 'WEBP'), ('.bmp', 'BMP'),
                              ('.gif', 'GIF'), ('.tiff', 'TIFF'), ('.heic', 'HEIF')):
            fixture.write('diagram' + suffix, generator.raster(kind))
        fixture.write('diagram.svg', b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"/>')
        result = fixture.commit()
        self.assertIn(b'images_allowed:7', result.stdout + result.stderr)
        remote = fixture.remote()
        fixture.git('push', remote, 'HEAD:refs/heads/main')
        fixture.write('ordinary.txt', b'normal update\n')
        fixture.commit()  # Existing images must not block subsequent commits.
        fixture.write('canary.txt', existing.CANARY)
        blocked = fixture.commit(ok=False)
        self.assertIn(b'REJECTED engine:python', blocked.stderr)
        self.assertIn(b'REJECTED engine:gitleaks', blocked.stderr)
        fixture.git('rm', '--cached', '--', 'canary.txt')
        fixture.write('renamed.jpg', png())  # Same bytes under a wrong extension.
        blocked = fixture.commit(ok=False)
        self.assertIn(b'image-format-or-structure', blocked.stderr)
        fixture.git('rm', '--cached', '--', 'renamed.jpg')
        fixture.write('renamed.txt', png())  # No exemption by blob identity alone.
        blocked = fixture.commit(ok=False)
        self.assertIn(b'ERROR engine:gitleaks', blocked.stderr)


if __name__ == '__main__':
    unittest.main()
