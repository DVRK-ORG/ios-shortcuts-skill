#!/usr/bin/env python3
"""build_shortcut.py — compile a JSON spec into an unsigned .shortcut (plist) file.

Usage:
    py build_shortcut.py spec.json                    # writes "<Name>.shortcut" (binary plist)
    py build_shortcut.py spec.json -o out.shortcut
    py build_shortcut.py spec.json --xml              # XML plist (nice for diff/review; `shortcuts sign` accepts it)
    py build_shortcut.py spec.json --stdout           # print the plist as JSON

Spec format: see assets/spec.schema.json and assets/example-hello.json.
The output is validated automatically with validate_shortcut.py rules; the build
fails (exit 1) if validation reports errors.

Text fields support {name} placeholders that reference an earlier action's "as"
name, plus {input} for Shortcut Input. Input fields accept "{name}", "$input"
(or "{input}"), "$var:Name", or a raw plist dict.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shortcut_lib import ShortcutBuilder  # noqa: E402
import validate_shortcut  # noqa: E402

try:  # keep UTF-8 printable on legacy Windows consoles (cp1252)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "shortcut"


def _resolve_params(value, builder):
    """Resolve {name} placeholders inside raw parameter values against earlier
    action outputs: strings with placeholders become token strings, and any
    nested dict/list is walked so raw actions get the same wiring as typed ones."""
    if isinstance(value, str):
        return builder._text(value)
    if isinstance(value, list):
        return [_resolve_params(v, builder) for v in value]
    if isinstance(value, dict):
        return {k: _resolve_params(v, builder) for k, v in value.items()}
    return value


def build(spec: dict) -> ShortcutBuilder:
    b = ShortcutBuilder(
        name=spec["name"],
        client_version=spec.get("clientVersion", "2700.0.4"),
        minimum_client_version=spec.get("minimumClientVersion", 900),
        icon=spec.get("icon"),
        types=spec.get("types"),
        input_classes=spec.get("inputClasses"),
        output_classes=spec.get("outputClasses"),
        has_output_fallback=spec.get("hasOutputFallback", False),
        has_input_variables=spec.get("hasInputVariables", False),
    )
    for s in spec.get("actions", []):
        do = s["do"]
        if do == "raw":
            b.raw(s["identifier"], _resolve_params(s.get("parameters"), b), s.get("as"))
        elif do == "text":
            b.text(s["text"], s.get("as"))
        elif do == "comment":
            b.comment(s["text"])
        elif do == "show":
            b.show(s["text"], s.get("as"))
        elif do == "alert":
            b.alert(s.get("title", ""), s["message"])
        elif do == "notify":
            b.notify(s["body"], s.get("title"), s.get("sound", True))
        elif do == "ask":
            b.ask(s["prompt"], s.get("inputType", "Text"), s.get("as"))
        elif do == "setvar":
            b.set_variable(s["name"], s.get("input"))
        elif do == "getvar":
            b.get_variable(s["name"], s.get("as"))
        elif do == "url":
            b.url(s["url"], s.get("as"))
        elif do == "openurl":
            b.open_url(s["url"])
        elif do == "download":
            b.download(s["url"], s.get("method", "GET"), s.get("as"), s.get("extra"))
        elif do == "quicklook":
            b.quicklook()
        elif do == "wait":
            b.wait(s.get("seconds", 1))
        elif do == "getdict":
            b.get_dict_value(s["key"], s.get("input"), s.get("as"))
        elif do == "getclipboard":
            b.get_clipboard(s.get("as") or "Clipboard")
        elif do == "setclipboard":
            b.set_clipboard(s.get("input"))
        elif do == "detectlinks":
            b.detect_links(s.get("input") or "{input}", s.get("as") or "URLs")
        elif do == "firstitem":
            b.get_first_item(s.get("input") or "{input}", s.get("as") or "First Item")
        elif do == "changecase":
            b.change_case(s.get("input") or "{input}", s.get("case", "lowercase"), s.get("as"))
        elif do == "replace":
            b.replace_text(
                s.get("input") or "{input}",
                s["find"],
                s.get("replace", ""),
                s.get("caseSensitive", False),
                s.get("regex", False),
                s.get("as"),
            )
        elif do == "calculate":
            op = s.get("operation")
            op = {"+": None, "*": "×", "/": "÷", "-": "-"}.get(op, op)
            b.calculate(op, s["operand"], s.get("input") or "{input}", s.get("as"))
        elif do == "sendmessage":
            b.send_message(s["content"], s["recipients"], s.get("showWhenRun", False), s.get("as"))
        elif do == "if":
            b.if_begin(s.get("input"), s.get("condition", 100), s.get("compare"), s.get("group"))
        elif do == "else":
            b.otherwise(s["group"])
        elif do == "endif":
            b.if_end(s["group"])
        elif do == "menu":
            b.menu_begin(s["items"], s.get("group"))
        elif do == "case":
            b.menu_case(s["title"], s["group"])
        elif do == "endmenu":
            b.menu_end(s["group"])
        elif do == "repeat":
            b.repeat_count_begin(s.get("count", 1), s.get("group"))
        elif do == "repeateach":
            b.repeat_each_begin(s.get("group"))
        elif do == "endblock":
            b.control_end(s["identifier"], s["group"])
        else:
            raise ValueError("unknown action type %r in spec" % do)
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spec", help="JSON spec file (see assets/spec.schema.json)")
    ap.add_argument("-o", "--output", help="output .shortcut path (default: '<Name>.shortcut' in cwd)")
    ap.add_argument("--xml", action="store_true", help="write XML plist instead of binary")
    ap.add_argument("--stdout", action="store_true", help="print plist as JSON instead of writing a file")
    ap.add_argument("--lint-target", choices=["ios", "macos"], default="ios", help="lint target for the auto-validation gate")
    ap.add_argument("--lint-min-os", type=int, default=26, help="minimum OS major version for the lint gate")
    args = ap.parse_args()

    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)

    b = build(spec)
    plist = b.to_plist()

    findings = validate_shortcut.validate(plist, target=args.lint_target, min_os=args.lint_min_os)
    for item in findings.items:
        if item["severity"] in ("error", "warning"):
            print("%s [%s] %s" % (item["severity"].upper(), item["code"], item["message"]))
    if findings.by("error"):
        print("validation failed — not writing output")
        sys.exit(1)

    if args.stdout:
        print(json.dumps(plist, indent=2, default=str))
        return

    out = args.output or (safe_filename(spec["name"]) + ".shortcut")
    parent = os.path.dirname(os.path.abspath(out))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    b.dump(out, fmt=plistlib.FMT_XML if args.xml else plistlib.FMT_BINARY)
    print("built %s (%d actions, %s plist)" % (out, len(b.actions), "XML" if args.xml else "binary"))
    print("next: lint with scripts/validate_shortcut.py, then deploy — see references/deployment-and-debugging.md")
    print("  iOS 15+ import needs a SIGNED file: on a Mac run  shortcuts sign --mode anyone --input %s --output signed.shortcut" % out)


if __name__ == "__main__":
    main()
