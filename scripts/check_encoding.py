#!/usr/bin/env python3
"""check_encoding.py — verify every text file is clean UTF-8 with LF endings.

    py scripts/check_encoding.py

Guards against a real failure mode: a UTF-8 file read as Windows-1252 (or any
single-byte codepage) and written back as UTF-8. The result imports fine, lints
fine, and renders on GitHub as mojibake — an em dash (U+2014) becomes "â€"".
The damage is invisible to a test that only checks for U+FFFD.

Detection is a round trip: if the file's text encodes to cp1252 and that byte
sequence decodes as UTF-8 into *different* text, the file is double-encoded.
Legitimate text does not survive that round trip.
"""
from __future__ import annotations

import os
import sys

TEXT_EXTENSIONS = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".svg", ".plist"}
REPLACEMENT = "\ufffd"
BOM = b"\xef\xbb\xbf"


def is_double_encoded(text: str) -> bool:
    """True if text looks like UTF-8 bytes that were decoded as cp1252."""
    try:
        raw = text.encode("cp1252")
    except UnicodeEncodeError:
        return False
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return decoded != text


def check(path: str, rel: str) -> list:
    problems = []
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(BOM):
        problems.append("%s: has a UTF-8 BOM" % rel)
        return problems
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        problems.append("%s: not valid UTF-8 (%s)" % (rel, exc))
        return problems
    if REPLACEMENT in text:
        problems.append("%s: contains U+FFFD (replacement character)" % rel)
    if is_double_encoded(text):
        problems.append("%s: text is double-encoded (UTF-8 read as cp1252 and written back)" % rel)
    if b"\r\n" in raw:
        problems.append("%s: contains CRLF line endings" % rel)
    return problems


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    problems = []
    checked = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "output")]
        for name in sorted(filenames):
            if os.path.splitext(name)[1].lower() not in TEXT_EXTENSIONS:
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            problems.extend(check(path, rel))
            checked += 1
    if problems:
        print("Encoding problems found:\n")
        for p in problems:
            print("  " + p)
        print("\n%d problem(s) in %d file(s) checked." % (len(problems), checked))
        return 1
    print("OK: %d text file(s) are clean UTF-8 with LF endings." % checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
