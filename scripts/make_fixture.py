#!/usr/bin/env python3
"""make_fixture.py — regenerate the deliberately-broken demo fixture.

    py scripts/make_fixture.py

Writes examples/broken-post-clipboard.shortcut (unsigned binary plist) from
examples/broken-post-clipboard.json with the same builder used for good
shortcuts, but with the lint gate bypassed so the fixture's intentional
errors survive. Used by docs/demo-walkthrough.md.
"""
from __future__ import annotations

import json
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_shortcut import build  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    spec_path = os.path.join(ROOT, "examples", "broken-post-clipboard.json")
    out_path = os.path.join(ROOT, "examples", "broken-post-clipboard.shortcut")
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    workflow = build(spec).to_plist()
    with open(out_path, "wb") as fh:
        plistlib.dump(workflow, fh, fmt=plistlib.FMT_BINARY)
    print("wrote %s (%d actions, intentional errors included)" % (out_path, len(workflow["WFWorkflowActions"])))


if __name__ == "__main__":
    main()
