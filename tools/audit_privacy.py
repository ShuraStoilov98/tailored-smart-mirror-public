#!/usr/bin/env python3
"""Scan reachable Git objects and working files for secrets and private metadata.

Run with detect-secrets installed for token/entropy coverage. Reports categories
and paths, never matched values. ZIP members are expanded. This cannot establish
consent, validate credentials, inspect remote-only objects or detect all secrets.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

PATTERNS = {
    "provider-token/private-key": re.compile(
        rb"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|"
        rb"gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)"),
    "private-network-address": re.compile(
        rb"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        rb"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
    "personal-local-path": re.compile(rb"(?:/(?:home|Users)/[^/\s]+/|[A-Z]:\\Users\\)")
}
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def git(*args):
    return subprocess.check_output(["git", *args])  # fixed executable, no shell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-only", action="store_true")
    args = parser.parse_args()
    findings, types = set(), Counter()
    try:
        from detect_secrets.core.scan import scan_file
        from detect_secrets.settings import default_settings, get_settings
    except ImportError:
        scan_file = None

    def scan(data, label):
        for category, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.add((category, label))
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for member in archive.infolist():
                    if member.file_size > 50 * 1024 * 1024:
                        findings.add(("oversized-archive-member", label))
                    else:
                        scan(archive.read(member), label + "::" + member.filename)
        if scan_file and b"\x00" not in data:
            with tempfile.NamedTemporaryFile(suffix=".txt") as temporary:
                temporary.write(data)
                temporary.flush()
                with default_settings():
                    get_settings().disable_filters(
                        "detect_secrets.filters.common.is_ignored_due_to_verification_policies"
                    )
                    for secret in scan_file(temporary.name):
                        findings.add(("detect-secrets: " + secret.type, label))

    objects = git("rev-list", "--objects", "--all").splitlines()
    for entry in objects:
        oid, _, path = entry.partition(b" ")
        kind = git("cat-file", "-t", oid.decode()).strip().decode()
        types[kind] += 1
        if kind in {"commit", "tag"}:
            data = git("cat-file", kind, oid.decode())
            for email in EMAIL.findall(data):
                if not email.endswith(b"@users.noreply.github.com"):
                    findings.add(("personal-commit-email", "commit/tag metadata"))
            scan(data, kind + " metadata")
        elif kind == "blob":
            scan(git("cat-file", "blob", oid.decode()), path.decode(errors="replace"))
    working_files = 0
    if not args.history_only:
        # Include tracked and nonignored untracked files.
        for entry in git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0"):
            if not entry:
                continue
            path = Path(entry.decode())
            if path.is_file():
                working_files += 1
                scan(path.read_bytes(), "worktree:" + path.as_posix())
    print(json.dumps({"objects": dict(types), "worktree_files": working_files,
                      "detect_secrets_enabled": bool(scan_file),
                      "findings": [{"category": category, "path": path}
                                   for category, path in sorted(findings)]}, indent=2))
    return 1 if findings else (0 if scan_file else 2)


if __name__ == "__main__":
    raise SystemExit(main())
