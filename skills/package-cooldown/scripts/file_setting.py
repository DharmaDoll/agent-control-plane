"""POSIX user config recipes for clients without a narrow native setter."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import tomllib

# Filename, table, key, and canonical on-disk value for an integer day count.
RECIPES = {
    "bun": (".bunfig.toml", "install", "minimumReleaseAge", lambda d: d * 86400),
    "uv": ("uv.toml", "", "exclude-newer", lambda d: f"{d} days"),
    "cargo": ("config.toml", "registry", "global-min-publish-age", lambda d: f"{d} days"),
    "gem": (".gemrc", "", ":cooldown", int),
}


def propose(tool, data, days):
    _, section, key, convert = RECIPES[tool]
    value = convert(days)
    if tool == "gem":
        # Ruby-specific YAML tags, aliases and duplicate keys need a native reader.
        if any(line.strip() and not line.lstrip().startswith("#") for line in data.splitlines()):
            raise ValueError("existing gemrc requires native inspection")
        return data + f"\n:cooldown: {value}\n"
    before = tomllib.loads(data)
    expected = copy.deepcopy(before)
    target = expected.setdefault(section, {}) if section else expected
    if not isinstance(target, dict) or key in target:
        raise ValueError("setting already present or table incompatible")
    target[key] = value
    line = f"{key} = {json.dumps(value)}\n"
    if not section:
        candidate = line + data
    elif section not in before:
        candidate = data + f"\n[{section}]\n" + line
    else:
        header = re.search(r"(?m)^\[" + section + r"\][ \t]*(?:#[^\n]*)?$", data)
        if not header:
            raise ValueError("table requires manual editing")
        candidate = data[:header.end()] + "\n" + line + data[header.end():]
    if tomllib.loads(candidate) != expected:
        raise ValueError("edit changes unrelated settings")
    return candidate


def snapshot(path):
    if path.is_symlink():
        raise ValueError("symlink target")
    if not path.exists():
        return None, b""
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError("unsafe target")
    if hasattr(os, "listxattr") and os.listxattr(path):
        raise ValueError("target has extended attributes; manual review required")
    return info, path.read_bytes()


def run(args):
    path = args.path
    filename, section, key, convert = RECIPES[args.tool]
    if (not path.is_absolute() or path.resolve() != path or
            not path.is_relative_to(Path.home().resolve()) or path.name != filename):
        raise ValueError("expected canonical user config path")
    for directory in path.parents:
        if directory.exists():
            state = directory.stat()
            if state.st_uid != os.getuid() or state.st_mode & 0o022:
                raise ValueError("user config directory has unsafe ownership or permissions")
        if directory == Path.home().resolve():
            break
    if not 1 <= args.days <= 36500:
        raise ValueError("days outside supported range")
    info, data = snapshot(path)
    candidate = propose(args.tool, data.decode(), args.days).encode()
    token = hashlib.sha256(repr((str(path), bool(info), data, candidate)).encode()).hexdigest()
    report = dict(path=str(path), key=".".join(filter(None, [section, key])),
                  old="absent", proposed=convert(args.days), review=token)
    if args.apply is None:
        return report
    if args.apply != token:
        raise ValueError("preview has changed")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(candidate)
        if info:
            os.chmod(name, stat.S_IMODE(info.st_mode) & 0o777)
            current, latest = snapshot(path)
            if current is None or (current.st_ino, current.st_ctime_ns, latest) != (
                    info.st_ino, info.st_ctime_ns, data):
                raise ValueError("target changed")
            os.replace(name, path)
        else:
            os.link(name, path)
    finally:
        Path(name).unlink(missing_ok=True)
    if path.read_bytes() != candidate:
        raise ValueError("post-write file check failed")
    return {**report, "stored": convert(args.days), "effective": "requires project check"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=RECIPES)
    parser.add_argument("path", type=Path)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--apply", metavar="REVIEW")
    try:
        print(json.dumps(run(parser.parse_args())))
    except (ValueError, OSError) as error:
        # Parser errors can quote private configuration. Only emit our own messages.
        message = str(error) if type(error) is ValueError else type(error).__name__
        parser.exit(2, f"Stopped: {message}\n")
