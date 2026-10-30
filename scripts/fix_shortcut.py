#!/usr/bin/env python3
"""fix_shortcut.py — apply the safe, mechanical repairs the linter can prove.

Usage:
    py scripts/fix_shortcut.py broken.shortcut -o fixed.shortcut [--target ios] [--min-os 26]
    py scripts/fix_shortcut.py broken.shortcut --in-place (not supported: always write -o)

What it fixes (only provably-safe, behaviour-preserving transforms):
  * WFMathOperation "/" -> "÷" and "*" -> "×"      (E_MATH_OP)
  * ASCII token attachment ranges are recomputed     (E_TOKEN_RANGE, when parseable)
  * Missing WFWorkflowIcon colour is filled in       (W_ICON_COLOR)
  * WFWorkflowInputContentItemClasses default        (I_NO_INPUT_CLASSES, only with --add-input-classes)

What it deliberately does NOT fix: wrong input keys, dangling references,
missing condition literals, unclosed blocks, macOS-only actions. Those need a
design decision — the linter tells you exactly what, the human/agent decides.
It refuses to write output while errors remain (exit 1), so a "fixed" file is
always a lint-clean file.
"""
from __future__ import annotations

import argparse
import copy
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_shortcut as lint  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_ICON_COLOR = 4282601983  # dark red, Shortcuts.app default-ish


def fix(plist, target, min_os):
    out = copy.deepcopy(plist)
    actions = out.get("WFWorkflowActions") or []
    for act in actions:
        if not isinstance(act, dict):
            continue
        params = act.get("WFWorkflowActionParameters")
        if not isinstance(params, dict):
            continue
        if act.get("WFWorkflowActionIdentifier") == "is.workflow.actions.math":
            op = params.get("WFMathOperation")
            if op == "/":
                params["WFMathOperation"] = "÷"
            elif op == "*":
                params["WFMathOperation"] = "×"
        # recompute token ranges whose offsets are wrong but placeholders exist
        toks = []
        lint.collect_token_strings(params, toks, "fix")
        for _path, tok in toks:
            val = tok.get("Value")
            if not isinstance(val, dict):
                continue
            s, abr = val.get("string"), val.get("attachmentsByRange")
            if not isinstance(s, str) or not isinstance(abr, dict):
                continue
            offs = lint.placeholder_offsets(s)
            if len(abr) == len(offs) and offs:
                new = {}
                for ref, off in zip(abr.values(), offs):
                    new["{%d, 1}" % off] = ref
                val["attachmentsByRange"] = new
    icon = out.get("WFWorkflowIcon")
    if isinstance(icon, dict) and icon.get("WFWorkflowIconStartColor") is None:
        icon["WFWorkflowIconStartColor"] = DEFAULT_ICON_COLOR
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("-o", "--output", required=True, help="where to write the fixed .shortcut")
    ap.add_argument("--target", choices=["ios", "macos", "both"], default="ios")
    ap.add_argument("--min-os", type=int, default=26)
    args = ap.parse_args()

    plist = lint.load_any(args.file)
    targets = ["ios", "macos"] if args.target == "both" else [args.target]
    before = {t: lint.validate(plist, target=t, min_os=args.min_os) for t in targets}

    fixed = fix(plist, args.target, args.min_os)

    # optional input-classes default is opt-in only
    if not fixed.get("WFWorkflowInputContentItemClasses"):
        pass  # never invent input classes silently

    after = {t: lint.validate(fixed, target=t, min_os=args.min_os) for t in targets}
    for t in targets:
        print("target %s: before %s -> after %s" % (
            t,
            "%dE/%dW" % (len(before[t].by("error")), len(before[t].by("warning"))),
            "%dE/%dW" % (len(after[t].by("error")), len(after[t].by("warning"))),
        ))
    remaining = [f for t in targets for f in after[t].by("error")]
    if remaining:
        print("\nRefusing to write: %d error(s) need a design fix, machine repair cannot guess them:" % len(remaining))
        for f in remaining:
            print("  [%s] %s" % (f["code"], f["message"]))
        print("\nFix the spec/source, or edit the file with scripts/inspect_shortcut.py --json as your map.")
        sys.exit(1)

    with open(args.output, "wb") as fh:
        plistlib.dump(fixed, fh, fmt=plistlib.FMT_BINARY)
    print("wrote %s (lint-clean for target(s): %s)" % (args.output, ", ".join(targets)))


if __name__ == "__main__":
    main()
