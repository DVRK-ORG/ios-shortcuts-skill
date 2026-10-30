#!/usr/bin/env python3
"""test_lint.py — proves the linter catches every failure mode it claims.

    py scripts/test_lint.py

Mirrors the classic broken-fixture suite: one workflow reproducing every
silent failure, a clean control, and the regression cases (off-by-one token
offset, Open URL's two legal keys, Otherwise with no input, forward vs
backward references, visible-output, and the iOS/macOS target diff).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_shortcut import validate  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append(cond)
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name, (" :: " + detail) if detail else ""))


def has(findings, code, severity="error"):
    return code in findings.codes(severity)


U1 = "7F3A4E91-C2D8-4B56-BE5A-0242AC120002"
U2 = "3B1C2D4E-5F60-4718-8293-A4B5C6D7E8F9"
PH = "￼"


def att(uuid, name="Text"):
    return {"Value": {"Type": "ActionOutput", "OutputUUID": uuid, "OutputName": name},
            "WFSerializationType": "WFTextTokenAttachment"}


def tok(text, ranges):
    return {"Value": {"string": text, "attachmentsByRange": ranges}, "WFSerializationType": "WFTextTokenString"}


ICON = {"WFWorkflowIconGlyphNumber": 59511, "WFWorkflowIconStartColor": 4278190080}

# ---------------------------------------------------------------- broken ----
broken = {
    "WFWorkflowName": "Broken",
    "WFWorkflowActions": [
        {"WFWorkflowActionIdentifier": "is.workflow.actions.runshellscript",
         "WFWorkflowActionParameters": {"UUID": "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", "WFScript": "echo hi"}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
         "WFWorkflowActionParameters": {"UUID": U1, "GroupingIdentifier": "GR-1", "WFCondition": 99, "WFControlFlowMode": 0}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.text.replace",
         "WFWorkflowActionParameters": {"UUID": U2, "text": "hello", "WFReplaceTextFind": "a"}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.math",
         "WFWorkflowActionParameters": {"UUID": "9E8D7C6B-5A49-4382-9170-6F5E4D3C2B1A", "WFMathOperation": "/", "WFMathOperand": "10"}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
         "WFWorkflowActionParameters": {"UUID": "1A2B3C4D-5E6F-4708-8192-A3B4C5D6E7F8",
          "WFTextActionText": tok("Hello " + PH + " world", {"{99, 1}": {"Type": "ActionOutput", "OutputUUID": "1A2B3C4D-5E6F-4708-8192-A3B4C5D6E7F8", "OutputName": "Text"}})}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.setclipboard",
         "WFWorkflowActionParameters": {"UUID": "2B3C4D5E-6F70-4819-92A3-B4C5D6E7F809", "WFInput": att("DEADBEEF-0000-0000-0000-000000000000", "Ghost")}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
         "WFWorkflowActionParameters": {"UUID": U2}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.setstoredcontent",
         "WFWorkflowActionParameters": {"UUID": "4C5D6E7F-8091-4A2B-93C4-D5E6F7081920"}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
         "WFWorkflowActionParameters": {"UUID": "5D6E7F80-91A2-4B3C-84D5-E6F708192031", "GroupingIdentifier": "GR-2", "WFControlFlowMode": 0}},
    ],
    "WFWorkflowClientVersion": 2773,
    "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 59511},
}

r = validate(broken, target="ios", min_os=26)
check("macOS-only action on iOS target", has(r, "E_MACOS_ONLY"))
check("conditional missing WFInput", has(r, "E_COND_NO_INPUT"))
check("conditional missing required literal", has(r, "E_COND_LITERAL"))
check("wrong action input key", has(r, "E_INPUT_KEY"))
check("ASCII division operator", has(r, "E_MATH_OP"))
check("token range / placeholder mismatch", has(r, "E_TOKEN_RANGE"))
check("dangling OutputUUID reference", has(r, "E_DANGLING_REF"))
check("duplicate UUID", has(r, "E_DUPLICATE_UUID"))
check("placeholder repeating-hex UUID", has(r, "E_PLACEHOLDER_UUID"))
check("OS 27 action on OS 26 target", has(r, "E_OS27_ACTION"))
check("unclosed control-flow group", has(r, "E_UNCLOSED_GROUP"))
check("missing icon colour", has(r, "W_ICON_COLOR", "warning"))

# ----------------------------------------------------------------- clean ----
clean = {
    "WFWorkflowName": "Clean",
    "WFWorkflowActions": [
        {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
         "WFWorkflowActionParameters": {"UUID": U1, "CustomOutputName": "Clipboard"}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
         "WFWorkflowActionParameters": {"UUID": U2, "CustomOutputName": "Text",
          "WFTextActionText": tok("Clipboard: " + PH, {"{11, 1}": {"Type": "ActionOutput", "OutputUUID": U1, "OutputName": "Clipboard"}})}},
        {"WFWorkflowActionIdentifier": "is.workflow.actions.showresult",
         "WFWorkflowActionParameters": {"UUID": "9E8D7C6B-5A49-4382-9170-6F5E4D3C2B1A", "Text": att(U2)}},
    ],
    "WFWorkflowClientVersion": 2773,
    "WFWorkflowIcon": ICON,
    "WFWorkflowInputContentItemClasses": ["public.plain-text"],
}
c = validate(clean, target="ios", min_os=26)
check("clean shortcut produces no errors", not c.by("error"), ",".join(c.codes("error")))

# off-by-one must be caught
import copy
shifted = copy.deepcopy(clean)
ts = shifted["WFWorkflowActions"][1]["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]
ts["attachmentsByRange"] = {"{12, 1}": list(ts["attachmentsByRange"].values())[0]}
check("off-by-one attachment offset is caught", has(validate(shifted, target="ios", min_os=26), "E_TOKEN_RANGE"))

# Open URL legally accepts WFInput OR WFURL
for key in ("WFInput", "WFURL"):
    wf = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
          "WFWorkflowActionParameters": {"UUID": U1, key: "x"}}], "WFWorkflowIcon": ICON}
    check("openurl with %s is not flagged" % key, not has(validate(wf, target="ios"), "E_INPUT_KEY"))

# Otherwise (mode 1) has no input by design
wf = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
      "WFWorkflowActionParameters": {"UUID": U1, "WFControlFlowMode": 1, "GroupingIdentifier": "G"}}], "WFWorkflowIcon": ICON}
check("Otherwise branch is not warned about missing input", not has(validate(wf, target="ios"), "W_NO_INPUT", "warning"))


def refwf(first_refs_second):
    a = {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
         "WFWorkflowActionParameters": {"UUID": U1, "CustomOutputName": "Clipboard"}}
    b = {"WFWorkflowActionIdentifier": "is.workflow.actions.setclipboard",
         "WFWorkflowActionParameters": {"UUID": U2, "WFInput": att(U1, "Clipboard")}}
    return {"WFWorkflowActions": [a, b] if first_refs_second else [b, a], "WFWorkflowIcon": ICON}


check("backward reference is not flagged", not has(validate(refwf(True), target="ios"), "W_FORWARD_REF", "warning"))
check("forward reference is flagged", has(validate(refwf(False), target="ios"), "W_FORWARD_REF", "warning"))

ends_data = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
             "WFWorkflowActionParameters": {"UUID": U1}}], "WFWorkflowIcon": ICON}
check("shortcut ending on a data action is flagged", has(validate(ends_data, target="ios"), "W_NO_VISIBLE_OUTPUT", "warning"))
ends_show = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.showresult",
             "WFWorkflowActionParameters": {"UUID": U1, "Text": "ok"}}], "WFWorkflowIcon": ICON}
check("shortcut ending with Show Content is not flagged", not has(validate(ends_show, target="ios"), "W_NO_VISIBLE_OUTPUT", "warning"))

# target diff: the same file is an error on iOS only
mac_only = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.runshellscript",
            "WFWorkflowActionParameters": {"UUID": U1, "WFScript": "echo hi"}}], "WFWorkflowIcon": ICON}
check("macOS-only action errors for ios target", has(validate(mac_only, target="ios"), "E_MACOS_ONLY"))
check("macOS-only action does NOT error for macos target", not has(validate(mac_only, target="macos"), "E_MACOS_ONLY"))

# the shipped examples must be lint-clean under the corrected condition codes
for name in ("example-hello", "example-api-guard"):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", name + ".json")
    if os.path.exists(path):
        import json as _json
        from build_shortcut import build
        wf = build(_json.load(open(path, encoding="utf-8"))).to_plist()
        res = validate(wf, target="ios", min_os=26)
        check("shipped example %s lints clean" % name, not res.by("error"), ",".join(res.codes("error")))

# deterministic UUID mode: the same seed must produce the same action UUIDs,
# so regenerating the committed demo fixture never dirties the repository.
import json as _json
from build_shortcut import build
from shortcut_lib import set_uuid_seed

_seed = "6f2b1c4e-8a3d-4f5b-9c2d-7e1a6b0d4f38"
_fixture_spec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples", "broken-post-clipboard.json")
if os.path.exists(_fixture_spec):
    _spec = _json.load(open(_fixture_spec, encoding="utf-8"))
    set_uuid_seed(_seed)
    _a = build(_spec).to_plist()
    set_uuid_seed(_seed)
    _b = build(_spec).to_plist()
    _uuids_a = [x["WFWorkflowActionParameters"]["UUID"] for x in _a["WFWorkflowActions"]]
    _uuids_b = [x["WFWorkflowActionParameters"]["UUID"] for x in _b["WFWorkflowActions"]]
    check("seeded build is reproducible", _uuids_a == _uuids_b)
    set_uuid_seed(None)
    _c = build(_spec).to_plist()
    _uuids_c = [x["WFWorkflowActionParameters"]["UUID"] for x in _c["WFWorkflowActions"]]
    check("unseeded build uses fresh UUIDs", _uuids_c != _uuids_a)
    _r = validate(_a, target="ios", min_os=26)
    _rm = validate(_a, target="macos", min_os=26)
    check("fixture fails on iOS with 6 errors", len(_r.by("error")) == 6, str(len(_r.by("error"))))
    check("fixture fails on macOS with 5 errors", len(_rm.by("error")) == 5, str(len(_rm.by("error"))))
    check("platform-only error is macOS_ONLY", "E_MACOS_ONLY" in _r.codes("error") and "E_MACOS_ONLY" not in _rm.codes("error"))

# ---------------------------------------------------------------------------
# Regressions from the 5-issue review. Each one shipped broken before; these
# checks exist so they cannot come back.
# ---------------------------------------------------------------------------

import fix_shortcut  # noqa: E402
import json  # noqa: E402

# --- 1. the fixer must never re-bind variables -----------------------------
# A plist may list its attachmentsByRange keys in any order. Re-binding
# attachments positionally swaps the variables: the file still imports and
# lints clean, but every value lands in the wrong field.

_UA = "7F3A4E91-C2D8-4B56-BE5A-0242AC120002"
_UB = "3B1C2D4E-5F60-4718-8293-A4B5C6D7E8F9"


def _ref(uuid, name):
    return {"Type": "ActionOutput", "OutputUUID": uuid, "OutputName": name}


def _swap_workflow(abr):
    return {
        "WFWorkflowName": "Swap",
        "WFWorkflowActions": [
            {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
             "WFWorkflowActionParameters": {"UUID": _UA, "CustomOutputName": "name"}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
             "WFWorkflowActionParameters": {"UUID": _UB, "CustomOutputName": "age"}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
             "WFWorkflowActionParameters": {"UUID": "9E8D7C6B-5A49-4382-9170-6F5E4D3C2B1A",
              "WFTextActionText": tok("Hello " + PH + " age " + PH, abr)}},
        ],
        "WFWorkflowIcon": ICON,
    }


def _abr_of(wf):
    return wf["WFWorkflowActions"][2]["WFWorkflowActionParameters"]["WFTextActionText"]["Value"]["attachmentsByRange"]


# one bad offset -> the single unanchored ref must take the single free slot
_bad = fix_shortcut.fix(_swap_workflow({"{14, 1}": _ref(_UB, "age"), "{6, 1}": _ref(_UA, "name")}), "ios", 26)
_fixed = _abr_of(_bad)
check("fixer repairs a single bad offset without swapping variables",
      _fixed.get("{6, 1}", {}).get("OutputName") == "name"
      and _fixed.get("{12, 1}", {}).get("OutputName") == "age",
      json.dumps(_fixed, sort_keys=True))
check("repaired token string lints clean", not validate(_bad, target="ios").by("error"))

# a correct file whose ranges happen to be listed out of order must be untouched
_ok = _swap_workflow({"{12, 1}": _ref(_UB, "age"), "{6, 1}": _ref(_UA, "name")})
_untouched = fix_shortcut.fix(_ok, "ios", 26)
check("fixer leaves an out-of-order but correct token string alone",
      _abr_of(_untouched) == _abr_of(_ok))
check("out-of-order token string is not an error", not validate(_ok, target="ios").by("error"))

# two broken offsets -> ambiguous, so the fixer must not guess
_amb = _swap_workflow({"{99, 1}": _ref(_UB, "age"), "{98, 1}": _ref(_UA, "name")})
check("fixer refuses an ambiguous token string",
      _abr_of(fix_shortcut.fix(_amb, "ios", 26)) == _abr_of(_amb))
check("ambiguous token string is still reported", has(validate(_amb, target="ios"), "E_TOKEN_RANGE"))

# --- 2. control-flow blocks must nest, not cross --------------------------

def _cond(gid, mode, uid):
    p = {"UUID": uid, "GroupingIdentifier": gid, "WFControlFlowMode": mode}
    if mode == 0:
        p["WFCondition"] = 100
        p["WFInput"] = {"Type": "Variable",
                        "Variable": {"Value": {"Type": "ExtensionInput"},
                                     "WFSerializationType": "WFTextTokenAttachment"}}
    return {"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
            "WFWorkflowActionParameters": p}


_cross = {"WFWorkflowActions": [
    _cond("g1", 0, _UA), _cond("g2", 0, _UB),
    _cond("g1", 2, "AA000000-0000-4000-8000-000000000001"),
    _cond("g2", 2, "AA000000-0000-4000-8000-000000000002")], "WFWorkflowIcon": ICON}
check("crossing control-flow blocks are caught", has(validate(_cross, target="ios"), "E_GROUP_NESTING"))

_nested = {"WFWorkflowActions": [
    _cond("g1", 0, _UA), _cond("g2", 0, _UB),
    _cond("g2", 2, "AA000000-0000-4000-8000-000000000001"),
    _cond("g1", 2, "AA000000-0000-4000-8000-000000000002")], "WFWorkflowIcon": ICON}
check("properly nested blocks are not flagged", not has(validate(_nested, target="ios"), "E_GROUP_NESTING"))

_orphan_branch = {"WFWorkflowActions": [_cond("g1", 1, _UA)], "WFWorkflowIcon": ICON}
check("an Otherwise with no open block is caught", has(validate(_orphan_branch, target="ios"), "E_ORPHAN_BRANCH"))

# --- 3. {input} must work inside text fields ------------------------------

_in_spec = {"name": "Input Test", "actions": [{"do": "show", "text": "You said {input}"}]}
_in_wf = build(_in_spec).to_plist()
_in_txt = _in_wf["WFWorkflowActions"][0]["WFWorkflowActionParameters"]["Text"]
check("{input} in a text field becomes a token string",
      _in_txt.get("WFSerializationType") == "WFTextTokenString")
check("{input} in a text field lints clean", not validate(_in_wf, target="ios").by("error"))

# --- 4. download bodies must carry attachments ----------------------------

_dl = build({"name": "Post", "actions": [
    {"do": "getclipboard", "as": "clip"},
    {"do": "download", "url": "https://api.example.com/post", "method": "POST", "as": "resp",
     "extra": {"WFRequestBody": {"Value": "payload: {clip}"}}}]}).to_plist()
_body = _dl["WFWorkflowActions"][1]["WFWorkflowActionParameters"]["WFRequestBody"]
check("download request body becomes a token string",
      isinstance(_body, dict) and _body.get("WFSerializationType") == "WFTextTokenString",
      json.dumps(_body, default=str))
check("download request body keeps no literal braces",
      not (isinstance(_body, dict) and isinstance(_body.get("Value"), dict)
           and "{" in _body["Value"].get("string", "")))
check("download body lints clean", not validate(_dl, target="ios").by("error"))

# --- 5. custom icons must use real plist keys -----------------------------

_friendly = build({"name": "Icon", "icon": {"glyph": 61440, "color": 431817727},
                   "actions": [{"do": "comment", "text": "x"}]}).to_plist()
check("friendly icon keys become real plist keys",
      _friendly["WFWorkflowIcon"] == {"WFWorkflowIconGlyphNumber": 61440, "WFWorkflowIconStartColor": 431817727},
      json.dumps(_friendly["WFWorkflowIcon"]))
check("friendly icon lints clean", not validate(_friendly, target="ios").by("error"))
_raw = build({"name": "Icon2", "icon": {"WFWorkflowIconGlyphNumber": 59511},
              "actions": [{"do": "comment", "text": "x"}]}).to_plist()
check("raw plist icon keys are still accepted",
      _raw["WFWorkflowIcon"] == {"WFWorkflowIconGlyphNumber": 59511})
_bad_icon = {"WFWorkflowActions": [{"WFWorkflowActionIdentifier": "is.workflow.actions.comment",
                                    "WFWorkflowActionParameters": {"UUID": _UA, "WFCommentActionText": "x"}}],
             "WFWorkflowIcon": {"glyph": 61440, "color": 431817727}}
check("unknown icon keys are an error", has(validate(_bad_icon, target="ios"), "E_ICON_KEYS"))

# --- 6. an attachment must agree with the action that produced it ---------

_mismatch = {"WFWorkflowActions": [
    {"WFWorkflowActionIdentifier": "is.workflow.actions.getclipboard",
     "WFWorkflowActionParameters": {"UUID": _UA, "CustomOutputName": "name"}},
    {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
     "WFWorkflowActionParameters": {"UUID": _UB,
      "WFTextActionText": tok("Hello " + PH, {"{6, 1}": _ref(_UA, "wrongName")})}}],
    "WFWorkflowIcon": ICON}
check("an attachment naming the wrong output is caught", has(validate(_mismatch, target="ios"), "E_TOKEN_REF"))

print("\n%d/%d passed" % (sum(RESULTS), len(RESULTS)))
sys.exit(0 if all(RESULTS) else 1)
