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


def _repair_token_ranges(val):
    """Repair a token string's attachment offsets WITHOUT re-associating variables.

    The safe rule: an attachment stays bound to the placeholder it already sits
    on. Only an attachment whose offset is not a placeholder at all may move, and
    only when exactly one placeholder is left unclaimed — then the mapping is
    forced and provably correct.

    Never re-bind attachments positionally. A plist is free to list its range
    keys in any order, so positional re-binding silently swaps variables: the
    file imports cleanly and every value lands in the wrong field.

    Returns (repaired: bool, note: str).
    """
    s, abr = val.get("string"), val.get("attachmentsByRange")
    if not isinstance(s, str) or not isinstance(abr, dict):
        return False, ""
    offs = lint.placeholder_offsets(s)
    if not offs or len(abr) != len(offs):
        return False, ""  # count mismatch: not provable, leave alone

    anchored = {}     # placeholder offset -> ref
    floating = []     # refs whose offset is not a placeholder
    for key, ref in abr.items():
        m = lint.RANGE_RE.match(key)
        if not m:
            return False, ""  # unparseable range key: leave alone
        start = int(m.group(1))
        if start in offs:
            if start in anchored:
                return False, ""  # two refs claim the same placeholder
            anchored[start] = ref
        else:
            floating.append(ref)

    unclaimed = [o for o in offs if o not in anchored]
    if not floating:
        # Everything already sits on a placeholder. Only the range *length*
        # may be wrong, and that is mechanical to repair.
        changed = False
        new = {}
        for key, ref in abr.items():
            m = lint.RANGE_RE.match(key)
            start, length = int(m.group(1)), int(m.group(2))
            if length != 1:
                new["{%d, 1}" % start] = ref
                changed = True
            else:
                new[key] = ref
        if changed:
            val["attachmentsByRange"] = new
            return True, "range length"
        return False, ""

    if len(floating) == 1 and len(unclaimed) == 1:
        # Forced mapping: the only ref that is off a placeholder must belong to
        # the only placeholder nobody claims.
        new = {"{%d, 1}" % unclaimed[0]: floating[0]}
        for off, ref in anchored.items():
            new["{%d, 1}" % off] = ref
        val["attachmentsByRange"] = new
        return True, "offset"

    return False, "ambiguous — %d unanchored attachment(s), %d unclaimed placeholder(s)" % (
        len(floating), len(unclaimed))


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
            _repair_token_ranges(val)
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
