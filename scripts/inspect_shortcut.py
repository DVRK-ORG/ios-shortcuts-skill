#!/usr/bin/env python3
"""inspect_shortcut.py — dump an unsigned .shortcut/.plist as a readable action list.

Usage:
    py inspect_shortcut.py file.shortcut
    py inspect_shortcut.py file.shortcut --json     # raw plist as JSON

Token strings are rendered with <Name> placeholders where variables/outputs are attached.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shortcut_lib import utf16_len  # noqa: E402
from validate_shortcut import load_any  # noqa: E402

try:  # keep emoji/UTF-8 printable on legacy Windows consoles (cp1252)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RANGE_RE = re.compile(r"^\{(\d+), (\d+)\}$")


def attachment_label(att) -> str:
    if not isinstance(att, dict):
        return str(att)
    t = att.get("Type")
    if t == "ActionOutput":
        return att.get("OutputName") or att.get("OutputUUID", "?")
    if t == "Variable":
        return "var:" + str(att.get("VariableName", "?"))
    if t == "ExtensionInput":
        return "ShortcutInput"
    return str(t or att)


def token_to_text(v: dict) -> str:
    val = v.get("Value", {})
    s = val.get("string", "")
    abr = val.get("attachmentsByRange", {})
    # Walk code points while tracking UTF-16 offsets (astral chars count as 2 units),
    # so a surrogate pair is never split apart.
    chars = list(s)
    off2idx = {}
    off = 0
    for idx, ch in enumerate(s):
        off2idx[off] = idx
        off += 2 if ord(ch) > 0xFFFF else 1
    for key, att in abr.items():
        m = RANGE_RE.match(key)
        if not m:
            continue
        start = int(m.group(1))
        if start in off2idx:
            chars[off2idx[start]] = "<%s>" % attachment_label(att)
    return "".join(chars)


def humanize(v, key=""):
    if isinstance(v, dict):
        if v.get("WFSerializationType") == "WFTextTokenString":
            return '"%s"' % token_to_text(v)
        if v.get("WFSerializationType") == "WFTextTokenAttachment":
            return "<%s>" % attachment_label(v.get("Value", {}))
        return "{ " + ", ".join("%s: %s" % (k, humanize(x)) for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(humanize(x) for x in v) + "]"
    if isinstance(v, str):
        return repr(v)
    return repr(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    plist = load_any(args.file)

    if args.json:
        print(json.dumps(plist, indent=2, default=str))
        return

    print("name:            %s" % plist.get("WFWorkflowName"))
    print("client version:  %s (min %s / %s)" % (
        plist.get("WFWorkflowClientVersion"),
        plist.get("WFWorkflowMinimumClientVersion"),
        plist.get("WFWorkflowMinimumClientVersionString"),
    ))
    print("types:           %s" % plist.get("WFWorkflowTypes"))
    print("input classes:   %s" % plist.get("WFWorkflowInputContentItemClasses"))
    print("output classes:  %s" % plist.get("WFWorkflowOutputContentItemClasses"))
    print("icon:            %s" % plist.get("WFWorkflowIcon"))
    actions = plist.get("WFWorkflowActions", [])
    print("actions: %d" % len(actions))
    print("-" * 70)
    for i, act in enumerate(actions):
        ident = act.get("WFWorkflowActionIdentifier", "?")
        params = act.get("WFWorkflowActionParameters", {})
        short = ident.replace("is.workflow.actions.", "")
        extra = []
        if "WFControlFlowMode" in params:
            extra.append("mode=%s" % params["WFControlFlowMode"])
        if "GroupingIdentifier" in params:
            extra.append("group=%s…" % str(params["GroupingIdentifier"])[:8])
        if "CustomOutputName" in params:
            extra.append("as=%s" % params["CustomOutputName"])
        suffix = ("  [" + ", ".join(extra) + "]") if extra else ""
        print("%3d. %s%s" % (i, short, suffix))
        for k, v in params.items():
            if k in ("UUID", "GroupingIdentifier", "WFControlFlowMode", "CustomOutputName"):
                continue
            print("      %s = %s" % (k, humanize(v, k)))


if __name__ == "__main__":
    main()
