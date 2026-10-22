"""Synthetic, local-only regression fixtures; never read personal images."""
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


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\0\0\0')) + chunk(b'IEND', b''))


def ftyp(major=b'heic', compatible=b'mif1', *, extended=False):
    body = major + b'\0' * 4 + compatible
    if extended:
        return struct.pack('>I4sQ', 1, b'ftyp', 16 + len(body)) + body
    return struct.pack('>I4s', 8 + len(body), b'ftyp') + body


# Synthetic recognition fixtures, intentionally not decodable image files.
HEADERS = {'.png': b'\x89PNG\r\n\x1a\n', '.jpg': b'\xff\xd8\xff',
           '.jpeg': b'\xff\xd8\xff', '.webp': b'RIFF\x10\0\0\0WEBPVP8 ',
           '.bmp': b'BM' + b'\0' * 12, '.gif': b'GIF89a',
           '.tif': b'II*\0', '.tiff': b'MM\0*', '.heic': ftyp()}


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
        (self.repo / 'diagram.png').write_bytes(png())
        self.git('add', '--', 'diagram.png')
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'images_allowed:1', result.stdout)

    def test_bad_image_header_is_incomplete_without_disclosure(self):
        (self.repo / 'disguised.png').write_bytes(b'private fixture contents')
        self.git('add', '--', 'disguised.png')
        result = self.scan('--staged')
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'image-signature-mismatch', result.stderr)
        self.assertNotIn(b'private fixture contents', result.stdout + result.stderr)
        self.assertNotIn(b'disguised.png', result.stdout + result.stderr)

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
    def test_extension_allowance_never_launches_decoder(self):
        with patch.object(policy.subprocess, 'run', side_effect=AssertionError('no image subprocess')):
            self.assertTrue(policy.Images().allow('photo.PNG', png()))
            self.assertFalse(policy.Images().allow('drawing.svg', b'<svg><script/></svg>'))

    def test_boundaries(self):
        for push, count, size in ((False, 100, 20 * 1024 * 1024), (True, 500, 50 * 1024 * 1024)):
            policy.enforce(count, size, push=push)
            for n, b in ((count + 1, size), (count, size + 1)):
                with self.assertRaises(policy.PolicyError):
                    policy.enforce(n, b, push=push)

    def test_malformed_updates_refuse(self):
        for raw in (b'x' * 65537, b'not an update\n'):
            with self.assertRaises(policy.PolicyError):
                policy.check_updates(raw)


class ImageAllowanceTests(unittest.TestCase):
    def test_plain_text_disguised_as_png_is_refused(self):
        with self.assertRaisesRegex(policy.PolicyError, '^image-signature-mismatch$'):
            policy.Images().allow('disguised.png', b'ordinary text, not PNG')

    def test_extensions_are_case_insensitive_and_body_is_unchecked(self):
        for suffix, header in HEADERS.items():
            for data in (header, header + b'not decoded\0'):
                with self.subTest(suffix=suffix, data_length=len(data)):
                    images = policy.Images()
                    self.assertTrue(images.allow('image' + suffix.upper(), data))
                    self.assertTrue(images.allow('copy' + suffix, data))
                    self.assertEqual(images.allowed, 1)
        for name in ('image.svg', 'image.png.txt', 'image.zip', 'image'):
            self.assertFalse(policy.Images().allow(name, b'anything'))

    def test_empty_short_wrong_headers_and_cache_context_refuse(self):
        for suffix, header in HEADERS.items():
            for data in (b'', b'not an image', header[:-1], b'prefix' + header):
                with self.subTest(suffix=suffix, data=data):
                    with self.assertRaisesRegex(policy.PolicyError, '^image-signature-mismatch$'):
                        policy.Images().allow('image' + suffix, data)
        images = policy.Images()
        images.allow('good.png', png())
        with self.assertRaisesRegex(policy.PolicyError, '^image-signature-mismatch$'):
            images.allow('wrong.jpg', png())

    def test_header_variants(self):
        variants = {'.gif': (b'GIF87a', b'GIF89a'),
                    '.tiff': (b'II*\0', b'MM\0*', b'II+\0\x08\0\0\0', b'MM\0+\0\x08\0\0'),
                    '.webp': tuple(b'RIFF\x10\0\0\0WEBP' + v for v in (b'VP8 ', b'VP8L', b'VP8X'))}
        for suffix, headers in variants.items():
            for header in headers:
                self.assertTrue(policy.Images().allow('image' + suffix, header))
        for data in (b'RIFF\x10\0\0\0WAVEVP8 ', b'RIFF\x10\0\0\0WEBPjunk'):
            with self.assertRaises(policy.PolicyError):
                policy.Images().allow('image.webp', data)

    def test_heic_brands_and_bounded_box(self):
        for brand in (b'heic', b'heix', b'heim', b'heis', b'hevc', b'hevx', b'hevm', b'hevs'):
            for extended in (False, True):
                self.assertTrue(policy.Images().allow('image.heic', ftyp(brand, extended=extended)))
                self.assertTrue(policy.Images().allow('image.heic', ftyp(b'mif1', brand, extended=extended)))
        self.assertTrue(policy.Images().allow('image.heic', ftyp(compatible=b'mif1' * 1020)))
        invalid = (ftyp(b'mif1', b'msf1'), ftyp(b'avif', b'mif1'), ftyp(b'isom', b'mp42'),
                   ftyp(b'mif1', b'mif1') + b'heic', ftyp(b'mif1', b'xheicxxx'),
                   b'\0\0\0\0' + ftyp()[4:], b'\xff' * 4 + ftyp()[4:],
                   ftyp()[:-1], ftyp(compatible=b'mif1' * 1021),
                   ftyp(b'mif1', b'mif1')[:12] + b'heic' + b'mif1')
        for data in invalid:
            with self.subTest(data_length=len(data)), self.assertRaises(policy.PolicyError):
                policy.Images().allow('image.heic', data)

    def test_image_byte_and_aggregate_limits(self):
        images = policy.Images()
        header = HEADERS['.png']
        self.assertTrue(images.allow('exact.png', header + b'x' * (policy.IMAGE_BYTES - len(header))))
        with self.assertRaisesRegex(policy.PolicyError, 'image-bytes-limit'):
            images.allow('large.png', b'x' * (policy.IMAGE_BYTES + 1))
        with patch.object(policy, 'PUSH_BYTES', len(header)):
            images = policy.Images()
            images.allow('a.png', header)
            with self.assertRaisesRegex(policy.PolicyError, 'image-scan-budget'):
                images.allow('b.png', header + b'd')
        images = policy.Images()
        for n in range(1000):
            images.allow('a.png', header + str(n).encode())
        with self.assertRaisesRegex(policy.PolicyError, 'image-scan-budget'):
            images.allow('a.png', header + b'new')

    def test_svg_is_not_parsed_or_exempted(self):
        svg = b'<!DOCTYPE svg><svg><script>example()</script></svg>'
        self.assertFalse(policy.Images().allow('active.svg', svg))


@unittest.skipUnless(os.environ.get('SECRET_CHECKS_RUNNER'), 'Runner required')
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
        for suffix, kind in (('.png', 'PNG'), ('.jpg', 'JPEG'), ('.webp', 'WEBP'), ('.bmp', 'BMP'),
                              ('.gif', 'GIF'), ('.tiff', 'TIFF'), ('.heic', 'HEIF')):
            fixture.write('diagram' + suffix, HEADERS[suffix])
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
        fixture.write('renamed.jpg', png())
        blocked = fixture.commit(ok=False)
        self.assertIn(b'DETAIL engine:python ERROR policy image-signature-mismatch', blocked.stderr)
        self.assertIn(b'DETAIL engine:gitleaks ERROR policy image-signature-mismatch', blocked.stderr)
        fixture.git('rm', '--cached', '--', 'renamed.jpg')
        fixture.write('renamed.txt', png())  # No exemption by blob identity alone.
        blocked = fixture.commit(ok=False)
        self.assertIn(b'ERROR engine:gitleaks', blocked.stderr)


if __name__ == '__main__':
    unittest.main()
