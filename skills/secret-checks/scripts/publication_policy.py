"""Shared, local-only publication budgets and bounded image validation."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

COMMIT_FILES = 100
COMMIT_BYTES = 20 * 1024 * 1024
PUSH_BLOBS = 500
PUSH_BYTES = 50 * 1024 * 1024
IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_PIXELS = 20_000_000
FORMATS = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.webp': 'WEBP',
           '.bmp': 'BMP', '.gif': 'GIF', '.tif': 'TIFF', '.tiff': 'TIFF',
           '.heic': 'HEIF', '.svg': 'SVG'}
OID = re.compile(rb'(?:[a-f0-9]{40}|[a-f0-9]{64})\Z')


class PolicyError(Exception):
    """Only fixed codes and numeric counters may cross the output boundary."""


def git(*args, data=None):
    env = dict(os.environ, GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
               GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
    try:
        r = subprocess.run(['/usr/bin/git', '--no-replace-objects', *args], input=data,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise PolicyError('git-unavailable') from None
    if r.returncode or len(r.stdout) > 32 * 1024 * 1024:
        raise PolicyError('git-incomplete')
    return r.stdout


def object_sizes(identities):
    if not identities:
        return []
    if len(identities) > 10000 or any(not OID.fullmatch(i) for i in identities):
        raise PolicyError('object-enumeration-limit')
    rows = git('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)',
               data=b'\n'.join(identities) + b'\n').splitlines()
    if len(rows) != len(identities):
        raise PolicyError('object-metadata-incomplete')
    result = []
    for expected, row in zip(identities, rows):
        fields = row.split()
        if len(fields) != 3 or fields[0] != expected or not fields[2].isdigit():
            raise PolicyError('object-metadata-invalid')
        result.append((fields[1], int(fields[2])))
    return result


def enforce(count, size, *, push=False):
    count_limit, byte_limit = (PUSH_BLOBS, PUSH_BYTES) if push else (COMMIT_FILES, COMMIT_BYTES)
    prefix = 'push' if push else 'commit'
    if count > count_limit:
        raise PolicyError(f'{prefix}-files actual:{count} limit:{count_limit}')
    if size > byte_limit:
        raise PolicyError(f'{prefix}-bytes actual:{size} limit:{byte_limit}')


def check_staged():
    changed = [p for p in git('diff', '--cached', '--no-ext-diff', '--name-only', '-z',
                             '--diff-filter=ACMRT').split(b'\0') if p]
    enforce(len(changed), 0)
    index = {}
    for entry in git('ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        fields, path = entry.split(b'\t', 1)
        mode, identity, stage = fields.split()
        if stage != b'0' or mode not in (b'100644', b'100755') or not OID.fullmatch(identity):
            raise PolicyError('unsupported-index')
        index[path] = identity
    try:
        objects = object_sizes([index[path] for path in changed])
    except KeyError:
        raise PolicyError('index-changed-during-check') from None
    if any(kind != b'blob' for kind, _ in objects):
        raise PolicyError('invalid-index-object')
    total = sum(size for _, size in objects)
    enforce(len(changed), total)
    return len(changed), total


def check_updates(raw, *, receive=False):
    if len(raw) > 65536:
        raise PolicyError('hook-input-limit')
    objects = set()
    for line in raw.splitlines():
        fields = line.split()
        if receive and len(fields) == 3:
            old, new, ref = fields
        elif not receive and len(fields) == 4:
            _, new, ref, old = fields
        else:
            raise PolicyError('invalid-hook-input')
        if not OID.fullmatch(old) or not OID.fullmatch(new) or len(old) != len(new):
            raise PolicyError('invalid-object-id')
        if not ref.startswith((b'refs/heads/', b'refs/tags/')):
            raise PolicyError('unsupported-ref')
        if set(new) == {48}:
            continue
        args = ['rev-list', '--objects', '--no-object-names', new.decode('ascii')]
        if set(old) != {48}:
            # Actual advertised old tip, not ambient remote-tracking refs. Fail
            # when unavailable; never fetch or assume a baseline was scanned.
            git('cat-file', '-e', old.decode('ascii'))
            args.append('^' + old.decode('ascii'))
        identities = git(*args).splitlines()
        if any(not OID.fullmatch(i) for i in identities):
            raise PolicyError('invalid-object-enumeration')
        objects.update(identities)
        if len(objects) > 10000:
            raise PolicyError('object-enumeration-limit')
    blobs = [size for kind, size in object_sizes(sorted(objects)) if kind == b'blob']
    total = sum(blobs)
    enforce(len(blobs), total, push=True)
    return len(blobs), total


def image_format(path):
    return FORMATS.get(PurePosixPath(path).suffix.lower())


class Images:
    def __init__(self):
        self.checked = set()
        self.allowed = 0
        self.bytes = 0

    def validate(self, path, data):
        """Return True only for verified raster data; SVG stays text-scanned."""
        kind = image_format(path)
        if kind is None:
            return False
        if len(data) > IMAGE_BYTES:
            raise PolicyError('image-bytes-limit')
        key = (kind, hashlib.sha256(data).digest())
        if key not in self.checked:
            self.bytes += len(data)
            if self.bytes > PUSH_BYTES or len(self.checked) >= 1000:
                raise PolicyError('image-scan-budget')
            try:
                result = subprocess.run(
                    [sys.executable, '-I', '-B', str(Path(__file__).with_name('image_worker.py')), kind],
                    input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                raise PolicyError('image-validation-unavailable-or-timeout') from None
            if result.returncode != 0 or result.stdout != b'VALID\n':
                # Fixed child codes only: never relay decoder exception strings.
                reason = {3: 'image-decoder-unavailable', 4: 'image-format-or-structure',
                          5: 'image-not-static', 6: 'image-dimensions', 7: 'svg-policy'}
                raise PolicyError(reason.get(result.returncode, 'image-validation-incomplete'))
            self.checked.add(key)
            if kind != 'SVG':
                self.allowed += 1
        return kind != 'SVG'

    def report(self):
        if self.allowed:
            print(f'POLICY images_allowed:{self.allowed} image_content:unscanned')
