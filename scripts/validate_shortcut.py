#!/usr/bin/env python3
"""validate_shortcut.py — target- and OS-aware lint for unsigned .shortcut files.

Usage:
    py scripts/validate_shortcut.py file.shortcut
    py scripts/validate_shortcut.py file.shortcut --target ios --min-os 26
    py scripts/validate_shortcut.py file.shortcut --target macos --json
    py scripts/validate_shortcut.py file.shortcut --fail-on-warning

Exit code 0 = no errors (and no warnings with --fail-on-warning), 1 otherwise.
Every finding carries a stable code (see references/lint-rules.md) so agents and
CI can act on it without parsing prose.

Checks: root shape, identifiers/parameters/UUIDs, platform gating (macOS-only,
Apple-Intelligence and OS-27 actions), control-flow balance, condition literals,
wrong action input keys, ASCII math operators, token-string UTF-16 offsets,
dangling/forward output references, and missing visible output.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shortcut_lib import A, PLACEHOLDER, utf16_len  # noqa: E402

try:  # keep UTF-8 printable on legacy Windows consoles (cp1252)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UUID_RE = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$")
RANGE_RE = re.compile(r"^\{(\d+), (\d+)\}$")
# Repeating-hex placeholder UUIDs (AAAAAAAA-…) that look valid but are fake.
REPEATING_HEX_RE = re.compile(
    r"^([0-9A-F])\1{7}-([0-9A-F])\2{3}-([0-9A-F])\3{3}-([0-9A-F])\4{3}-([0-9A-F])\5{11}$"
)

CONTROL_IDS = {A + "conditional", A + "choosefrommenu", A + "repeat.count", A + "repeat.each"}

# --- findings ---------------------------------------------------------------

class Findings:
    """Collects coded findings: (severity, code, message, action_index, action_id)."""

    def __init__(self):
        self.items = []

    def _add(self, severity, code, message, index=None, ident=None):
        self.items.append({"severity": severity, "code": code, "message": message,
                           "actionIndex": index, "actionId": ident})

    def error(self, code, message, index=None, ident=None):
        self._add("error", code, message, index, ident)

    def warn(self, code, message, index=None, ident=None):
        self._add("warning", code, message, index, ident)

    def note(self, code, message, index=None, ident=None):
        self._add("info", code, message, index, ident)

    def by(self, severity):
        return [f for f in self.items if f["severity"] == severity]

    def codes(self, severity=None):
        return [f["code"] for f in self.items if severity is None or f["severity"] == severity]


# --- condition / platform / input-key tables (references/lint-rules.md) -----

CONDITION_CODES = {
    0: "is less than", 1: "is less than or equal to", 2: "is greater than",
    3: "is greater than or equal to", 4: "is (string equals)", 5: "is not (string)",
    8: "begins with", 9: "ends with", 99: "contains", 999: "does not contain",
    100: "has any value", 101: "does not have any value", 1002: "is today", 1003: "is between",
}
STRING_CODES = {4, 5, 8, 9, 99, 999}
NUMERIC_CODES = {0, 1, 2, 3}
EXISTENCE_CODES = {100, 101}

MACOS_ONLY_ACTIONS = {
    A + "runshellscript", A + "runapplescript", A + "runjavascriptforautomation",
    A + "getmacmodelname",
}
AI_ACTIONS = {
    A + "askllm", A + "createimage", A + "adjusttoneoftext", A + "makelistfromtext",
    A + "maketablefromtext", A + "proofreadtext", A + "rewritetext",
    A + "summarizetext", A + "openvisualintelligence",
}
OS27_ACTIONS = {
    A + "getstoredcontent", A + "setstoredcontent", A + "deletestoredcontent", A + "additemtolist",
}

# Action -> key(s) its main input/value may legitimately arrive under.
ACTION_INPUT_KEYS = {
    A + "text.replace": ["WFInput"], A + "replace": ["WFInput"],
    A + "text.changecase": ["text"], A + "text.split": ["text"], A + "text.combine": ["text"],
    A + "gettext": ["WFTextActionText"], A + "alert": ["WFAlertActionTitle"],
    A + "notification": ["WFNotificationTitle"], A + "ask": ["WFAskActionPrompt"],
    A + "setvariable": ["WFVariableName"], A + "getvariable": ["WFVariable"],
    A + "count": ["WFCountType"], A + "openurl": ["WFInput", "WFURL"],
    A + "url": ["WFURLActionURL"], A + "getclipboard": ["WFClipboardActionContent"],
    A + "setclipboard": ["WFInput"], A + "openapp": ["WFAppName"],
    A + "getvalueforkey": ["WFDictionaryKey"], A + "math": ["WFMathOperand"],
    A + "choosefrommenu": ["WFMenuPrompt"], A + "choosefromlist": ["WFChooseFromListActionPrompt"],
    A + "runworkflow": ["WFWorkflowName"], A + "comment": ["WFCommentActionText"],
    A + "getwebpagecontents": ["WFURL"], A + "downloadurl": ["WFURL"],
    A + "documentpicker.save": ["WFInput"], A + "file.append": ["WFInput"],
    A + "speaktext": ["WFSpeakTextText"], A + "base64encode": ["WFInput"],
}
GENERIC_INPUT_KEYS = {"WFInput"}  # generic variable-picker key; never "misplaced"
_SPECIFIC_OWNERS = {}
for _act, _keys in ACTION_INPUT_KEYS.items():
    for _k in _keys:
        _SPECIFIC_OWNERS.setdefault(_k, []).append(_act)

VARIABLE_INPUT_ACTIONS = {
    A + "conditional", A + "repeat.each", A + "setclipboard", A + "setvariable",
    A + "count", A + "getvalueforkey", A + "openurl", A + "base64encode", A + "text.replace",
}

VISIBLE_OUTPUT_ACTIONS = {
    A + "showresult", A + "alert", A + "notification", A + "share",
    A + "documentpicker.save", A + "file.append",
}
EMPTY_TEXT_KEYS = {
    "WFTextActionText", "WFAlertActionTitle", "WFNotificationTitle", "WFAskActionPrompt",
    "WFCommentActionText", "WFVariableName",
}


# --- traversal helpers -------------------------------------------------------

def utf16_char_at(s: str, offset: int) -> str:
    """Char at a UTF-16 code-unit offset ('?' when the offset splits a surrogate pair)."""
    raw = s.encode("utf-16-le")
    chunk = raw[offset * 2: offset * 2 + 2]
    try:
        return chunk.decode("utf-16-le")
    except UnicodeDecodeError:
        return "?"


def placeholder_offsets(s: str) -> list:
    """UTF-16 offsets of every U+FFFC placeholder in s."""
    offs, off = [], 0
    for ch in s:
        if ch == PLACEHOLDER:
            offs.append(off)
        off += 2 if ord(ch) > 0xFFFF else 1
    return offs


def walk(obj, fn):
    if isinstance(obj, dict):
        fn(obj)
        for v in obj.values():
            walk(v, fn)
    elif isinstance(obj, list):
        for v in obj:
            walk(v, fn)


def collect_refs(obj, out):
    """Every attachment reference dict (Type/ActionOutput/Variable/…)."""
    if isinstance(obj, dict):
        t = obj.get("WFSerializationType")
        if t == "WFTextTokenAttachment" and isinstance(obj.get("Value"), dict):
            out.append(obj["Value"])
            return  # do not double-descend into reference payloads
        if t == "WFTextTokenString":
            abr = obj.get("Value", {})
            abr = abr.get("attachmentsByRange") if isinstance(abr, dict) else None
            if isinstance(abr, dict):
                for ref in abr.values():
                    if isinstance(ref, dict):
                        out.append(ref)
            return
        for v in obj.values():
            collect_refs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_refs(v, out)


def collect_token_strings(obj, out, path=""):
    if isinstance(obj, dict):
        if obj.get("WFSerializationType") == "WFTextTokenString":
            out.append((path, obj))
            return
        for k, v in obj.items():
            collect_token_strings(v, out, "%s.%s" % (path, k) if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            collect_token_strings(v, out, "%s[%d]" % (path, i))


# --- the linter ---------------------------------------------------------------

def validate(plist, target="ios", min_os=26):
    """Return a Findings object for a WFWorkflow plist dict.

    target: 'ios' | 'macos' | 'both'. min_os: minimum OS major version (26 default).
    """
    f = Findings()
    if not isinstance(plist, dict):
        f.error("E_ROOT", "Root of the file is not a dictionary — this is not a Shortcuts workflow plist.")
        return f
    actions = plist.get("WFWorkflowActions")
    if not isinstance(actions, list):
        f.error("E_NO_ACTIONS", "Missing WFWorkflowActions array. The file has no actions at all.")
        return f
    if not actions:
        f.warn("W_EMPTY", "The shortcut contains zero actions — it will do nothing when run.")

    # top level
    if not plist.get("WFWorkflowName"):
        f.warn("W_NO_NAME", "WFWorkflowName missing — the file name becomes the shortcut name on import.")
    if not plist.get("WFWorkflowClientVersion") and not plist.get("WFWorkflowClientRelease"):
        f.warn("W_NO_CLIENT_VERSION", "No WFWorkflowClientVersion/Release. Shortcuts may re-save it on first open.")
    icon = plist.get("WFWorkflowIcon")
    if not isinstance(icon, dict):
        f.warn("W_NO_ICON", "No WFWorkflowIcon set — the shortcut gets a generic icon.")
    else:
        if icon.get("WFWorkflowIconGlyphNumber") is None:
            f.warn("W_ICON_GLYPH", "WFWorkflowIcon is missing WFWorkflowIconGlyphNumber.")
        if icon.get("WFWorkflowIconStartColor") is None:
            f.warn("W_ICON_COLOR", "WFWorkflowIcon is missing WFWorkflowIconStartColor.")
    if not plist.get("WFWorkflowInputContentItemClasses"):
        f.note("I_NO_INPUT_CLASSES", "No WFWorkflowInputContentItemClasses — the shortcut declares no accepted input types.")
    if "WFWorkflowTypes" in plist and not isinstance(plist.get("WFWorkflowTypes"), list):
        f.warn("W_TYPES_SHAPE", "WFWorkflowTypes should be an array.")
    if "WFQuickActionSurfaces" in plist and not isinstance(plist.get("WFQuickActionSurfaces"), list):
        f.warn("W_SURFACES_SHAPE", "WFQuickActionSurfaces should be an array.")
    mc = plist.get("WFWorkflowMinimumClientVersion")
    if isinstance(mc, int) and not isinstance(mc, bool) and mc >= 1100:
        f.note("I_SIGNED_IMPORT", "WFWorkflowMinimumClientVersion >= 1100 targets iOS 15+, where importing "
                                  "a file requires a SIGNED (AEA1) .shortcut — sign on a Mac "
                                  "(`shortcuts sign --mode anyone`) or share via an iCloud link.")

    uuids = {}            # uuid -> action index
    groups = {}           # GroupingIdentifier -> members [(index, ident, mode)]
    for i, act in enumerate(actions):
        where = "action[%d]" % i
        if not isinstance(act, dict):
            f.error("E_BAD_ACTION", "%s is not a dict." % where, i)
            continue
        ident = act.get("WFWorkflowActionIdentifier")
        params = act.get("WFWorkflowActionParameters")
        if not isinstance(ident, str) or not ident:
            f.error("E_NO_IDENTIFIER", "%s is missing WFWorkflowActionIdentifier." % where, i)
            ident = ""
        if params is None:
            f.warn("W_NO_PARAMS", "%s (%s) has no WFWorkflowActionParameters dictionary." % (where, ident), i, ident or None)
            params = {}
        if not isinstance(params, dict):
            f.error("E_BAD_PARAMS", "%s (%s) WFWorkflowActionParameters is not a dictionary." % (where, ident), i, ident or None)
            continue

        # UUID hygiene
        u = params.get("UUID")
        if u is not None:
            if not isinstance(u, str) or not UUID_RE.match(u):
                f.error("E_BAD_UUID", '%s (%s) UUID %r is not an uppercase 8-4-4-4-12 hex string.' % (where, ident, u), i, ident)
            elif REPEATING_HEX_RE.match(u):
                f.error("E_PLACEHOLDER_UUID", '%s (%s) UUID %r is a repeating-hex placeholder, not a real generated UUID.' % (where, ident, u), i, ident)
            elif u in uuids:
                f.error("E_DUPLICATE_UUID", '%s (%s) UUID %s is already used by action[%d]. Every action needs a unique UUID.' % (where, ident, u, uuids[u]), i, ident)
            else:
                uuids[u] = i

        # platform gating
        if target == "ios" and ident in MACOS_ONLY_ACTIONS:
            f.error("E_MACOS_ONLY", '"%s" only exists on macOS. This shortcut will fail on iPhone/iPad.' % ident, i, ident)
        if target == "ios" and ident in AI_ACTIONS:
            f.warn("W_AI_DEVICE", '"%s" needs an Apple Intelligence device (iPhone 15 Pro or later). Older devices cannot run it.' % ident, i, ident)
        if min_os < 27 and ident in OS27_ACTIONS:
            f.error("E_OS27_ACTION", '"%s" requires OS 27 or later, but the target is OS %s.' % (ident, min_os), i, ident)
        if ident and not ident.startswith(A):
            f.warn("W_FOREIGN_IDENTIFIER", 'Identifier %r is not a standard is.workflow.actions.* id. Third-party App Intent actions are valid but cannot be validated here.' % ident, i, ident)
        if ident == A + "input":
            f.warn("W_LEGACY_INPUT", "%s uses is.workflow.actions.input — prefer an ExtensionInput attachment for share-sheet input." % where, i, ident)

        # control flow bookkeeping
        mode = params.get("WFControlFlowMode")
        if mode is not None and (not isinstance(mode, int) or isinstance(mode, bool)):
            f.error("E_MODE_TYPE", '%s (%s) WFControlFlowMode must be an <integer>, got %r.' % (where, ident, mode), i, ident)
        gid = params.get("GroupingIdentifier")
        if ident in CONTROL_IDS:
            if not isinstance(gid, str) or not gid:
                f.error("E_GROUPING_ID", "%s (%s) control-flow action missing GroupingIdentifier." % (where, ident), i, ident)
        if isinstance(gid, str) and gid:
            groups.setdefault(gid, []).append((i, ident, mode))

        # conditions
        if ident == A + "conditional" and mode == 0:
            code = params.get("WFCondition")
            if code is not None and not isinstance(code, int):
                f.warn("W_CONDITION_STRING", 'WFCondition is the string %r. Use an integer operator code (%s) — string names may import but degrade at runtime.' % (code, ", ".join(str(c) for c in CONDITION_CODES)), i, ident)
            elif isinstance(code, int) and code not in CONDITION_CODES:
                f.warn("W_UNKNOWN_CONDITION", "WFCondition code %s is not a documented operator code (see references/lint-rules.md)." % code, i, ident)
            if "WFConditions" not in params and not params.get("WFInput"):
                f.error("E_COND_NO_INPUT", "If action (WFControlFlowMode 0) has no WFInput. Every condition needs an explicit input variable.", i, ident)
            if isinstance(code, int):
                needed = "WFConditionalActionString" if code in STRING_CODES else "WFNumberValue" if code in NUMERIC_CODES else None
                if needed and params.get(needed) is None:
                    f.error("E_COND_LITERAL", 'Condition "%s" (code %s) requires %s, which is missing.' % (CONDITION_CODES.get(code, "?"), code, needed), i, ident)
                if code in EXISTENCE_CODES and (params.get("WFConditionalActionString") is not None or params.get("WFNumberValue") is not None):
                    f.warn("W_COND_EXTRA_LITERAL", 'Condition "%s" (code %s) takes no literal value, but one is set.' % (CONDITION_CODES[code], code), i, ident)
            if "WFConditions" in params and "WFCondition" in params:
                f.warn("W_MIXED_CONDITIONS", "This action has both WFConditions and top-level WFCondition. Do not mix the two patterns.", i, ident)

        # math operators — ASCII / and * silently render as + in Shortcuts
        if ident == A + "math":
            op = params.get("WFMathOperation")
            if op in ("*", "/"):
                want = "× (U+00D7)" if op == "*" else "÷ (U+00F7)"
                f.error("E_MATH_OP", 'WFMathOperation %r is wrong — Shortcuts expects %s. ASCII operators silently render as "+".' % (op, want), i, ident)
            operand = params.get("WFMathOperand")
            if operand is not None and not isinstance(operand, (str, int, float)):
                f.warn("W_MATH_OPERAND", "WFMathOperand should be a plain literal string, not a wrapped dict.", i, ident)

        # wrong input key → imports cleanly, shows an empty field at runtime
        accepted = ACTION_INPUT_KEYS.get(ident)
        if accepted:
            has_accepted = any(params.get(k) is not None for k in accepted)
            misplaced = []
            for k in params:
                if k in accepted or k in GENERIC_INPUT_KEYS:
                    continue
                owners = _SPECIFIC_OWNERS.get(k)
                if owners and ident not in owners:
                    misplaced.append((k, owners[0]))
            if not has_accepted and misplaced:
                key, owner = misplaced[0]
                f.error("E_INPUT_KEY", '"%s" should take "%s" but has "%s" instead (that key belongs to %s). It will import but show an empty field.' % (ident, '" or "'.join(accepted), key, owner), i, ident)

        # actions that need a wired input
        if ident in VARIABLE_INPUT_ACTIONS and mode in (None, 0):
            has_input = any(params.get(k) is not None for k in
                            ("WFInput", "WFVariable", "WFTextActionText", "text", "WFURL", "WFURLActionURL"))
            if not has_input and not params.get("CustomOutputName"):
                f.warn("W_NO_INPUT", '"%s" has no input wired and no CustomOutputName — it will likely operate on an empty value.' % ident, i, ident)

        # empty required text + blank location payloads
        for k, v in params.items():
            if v == "" and k in EMPTY_TEXT_KEYS:
                f.warn("W_EMPTY_FIELD", 'Parameter "%s" is an empty string.' % k, i, ident)
        for k in ("WFLocation", "WFWeatherCustomLocation", "WFWeatherLocation"):
            v = params.get(k)
            if isinstance(v, str) and v.strip() == "":
                f.error("E_EMPTY_LOCATION", "%s is blank. Location parameters must reference a real location output." % k, i, ident)
            elif isinstance(v, dict) and v.get("WFSerializationType") == "WFTextTokenString":
                s = v.get("Value", {})
                s = s.get("string") if isinstance(s, dict) else None
                if isinstance(s, str) and s.strip() == "":
                    f.error("E_EMPTY_LOCATION", "%s points at an empty string." % k, i, ident)

        # token strings: ranges must land exactly on U+FFFC placeholders (UTF-16)
        toks = []
        collect_token_strings(params, toks, "%s.parameters" % where)
        for path, tok in toks:
            val = tok.get("Value")
            if not isinstance(val, dict):
                f.error("E_TOKEN_RANGE", "Token string at %s has a non-dict Value." % path, i, ident)
                continue
            s, abr = val.get("string"), val.get("attachmentsByRange")
            if not isinstance(s, str) or not isinstance(abr, dict):
                f.error("E_TOKEN_RANGE", "Token string at %s is missing string/attachmentsByRange." % path, i, ident)
                continue
            offs = placeholder_offsets(s)
            bad = []
            if len(abr) != len(offs):
                bad.append("has %d attachment range(s) but %d placeholder character(s)" % (len(abr), len(offs)))
            for key in abr:
                m = RANGE_RE.match(key)
                if not m:
                    bad.append("%r is not a '{start, length}' key" % key)
                    continue
                start, length = int(m.group(1)), int(m.group(2))
                if length != 1:
                    bad.append("range %r length must be 1" % key)
                if start not in offs:
                    bad.append("range %r points at UTF-16 offset %d, which is not a placeholder (placeholders at %s)"
                               % (key, start, ", ".join(str(o) for o in offs) or "none"))
            if bad:
                f.error("E_TOKEN_RANGE", "Token string at %s: %s." % (path, "; ".join(bad)), i, ident)
            if PLACEHOLDER in s and not abr:
                f.warn("W_TOKEN_NO_ATTACH", "Token string at %s contains U+FFFC but attachmentsByRange is empty." % path, i, ident)

    # control-flow balance: every opener needs a matching closer, same identifier
    for gid, members in groups.items():
        starts = [m for m in members if m[2] == 0]
        ends = [m for m in members if m[2] == 2]
        if starts and not ends:
            f.error("E_UNCLOSED_GROUP", 'Control-flow group "%s" opens at action[%d] but never closes. Add a matching end action with the same GroupingIdentifier.' % (gid, starts[0][0]), starts[0][0], starts[0][1])
        if ends and not starts:
            f.error("E_ORPHAN_END", 'Control-flow group "%s" has an end action at action[%d] but no opener.' % (gid, ends[0][0]), ends[0][0], ends[0][1])
        if len(starts) > 1:
            f.warn("W_GROUP_MULTI", 'Control-flow group "%s" has %d openers.' % (gid, len(starts)), starts[1][0], starts[1][1])
        opener_ids = {m[1] for m in members if m[2] == 0}
        for idx, mid, _mode in members:
            if _mode == 2 and opener_ids and mid not in opener_ids:
                f.error("E_GROUP_ID_MISMATCH", "action[%d] end-block identifier %s does not match the block opener %s." % (idx, mid, "/".join(sorted(opener_ids))), idx, mid)

    # references: dangling + forward
    index_of = dict(uuids)
    for i, act in enumerate(actions):
        if not isinstance(act, dict):
            continue
        params = act.get("WFWorkflowActionParameters")
        if not isinstance(params, dict):
            continue
        refs = []
        collect_refs(params, refs)
        for ref in refs:
            if not isinstance(ref, dict) or ref.get("Type") != "ActionOutput":
                continue
            target_uuid = ref.get("OutputUUID")
            if not target_uuid:
                continue
            if target_uuid not in index_of:
                f.error("E_DANGLING_REF", "action[%d] references OutputUUID %s, which no action in this shortcut declares." % (i, target_uuid), i, act.get("WFWorkflowActionIdentifier"))
            elif index_of[target_uuid] > i:
                f.warn("W_FORWARD_REF", "action[%d] references output of action[%d], which runs AFTER it. The value will be empty when this action runs." % (i, index_of[target_uuid]), i, act.get("WFWorkflowActionIdentifier"))

    # unused outputs (info only — comments and terminal actions are fine)
    referenced = set()
    all_refs = []
    collect_refs({"WFWorkflowActions": actions}, all_refs)
    for ref in all_refs:
        if isinstance(ref, dict) and ref.get("Type") == "ActionOutput" and ref.get("OutputUUID"):
            referenced.add(ref["OutputUUID"])
    for i, act in enumerate(actions):
        if not isinstance(act, dict):
            continue
        params = act.get("WFWorkflowActionParameters")
        if isinstance(params, dict):
            u = params.get("UUID")
            if u and u not in referenced:
                f.note("I_UNUSED_OUTPUT", "action[%d] (%s) produces output that nothing references." % (i, act.get("WFWorkflowActionIdentifier")), i, act.get("WFWorkflowActionIdentifier"))

    # visible output: ending on a data action reads as "it did nothing"
    if actions and isinstance(actions[-1], dict):
        last = actions[-1]
        last_id = last.get("WFWorkflowActionIdentifier", "")
        last_params = last.get("WFWorkflowActionParameters") or {}
        if last_id not in VISIBLE_OUTPUT_ACTIONS and last_params.get("WFControlFlowMode") != 2:
            f.warn("W_NO_VISIBLE_OUTPUT", 'The shortcut ends with "%s", which produces a value but shows nothing to the user. End with Show Content (showresult), Show Alert, or Show Notification so running it has visible feedback.' % (last_id or "?"), len(actions) - 1, last_id or None)
    return f


def load_any(path):
    """Load an unsigned .shortcut/.plist; exits with guidance on signed AEA1 files."""
    with open(path, "rb") as fh:
        head = fh.read(8)
    if head[:4] == b"AEA1":
        sys.exit(
            "This is a SIGNED Apple Encrypted Archive (magic AEA1). The payload is encrypted; "
            "you cannot read it directly. Get the unsigned plist via one of:\n"
            "  - Mac: open it in Shortcuts.app, or read ZDATA from ~/Library/Shortcuts/Shortcuts.sqlite\n"
            "  - iCloud share link: the API field fields.shortcut.value.downloadURL serves the unsigned plist\n"
            "  - or rebuild from a spec with scripts/build_shortcut.py\n"
            "See references/file-format.md -> 'Getting the unsigned plist out of a signed file'."
        )
    with open(path, "rb") as fh:
        return plistlib.load(fh)


def format_human(findings: Findings, path, target, min_os):
    lines = ["Linting %s  (target: %s, min OS: %s)" % (path, target, min_os)]
    summary = "%d error(s), %d warning(s), %d info" % (
        len(findings.by("error")), len(findings.by("warning")), len(findings.by("info")))
    for item in findings.items:
        loc = ""
        if item["actionIndex"] is not None:
            loc = "  (action[%d] %s)" % (item["actionIndex"], item["actionId"] or "")
        mark = {"error": "ERROR", "warning": "WARN", "info": "INFO"}[item["severity"]]
        lines.append("%-5s [%s] %s%s" % (mark, item["code"], item["message"], loc))
    lines.append(summary)
    lines.append("FAILED" if findings.by("error") else "PASSED: no errors")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file")
    ap.add_argument("--target", choices=["ios", "macos", "both"], default="ios")
    ap.add_argument("--min-os", type=int, default=26)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-warning", action="store_true", help="exit 1 when warnings are present too")
    args = ap.parse_args()

    targets = ["ios", "macos"] if args.target == "both" else [args.target]
    plist = load_any(args.file)
    exit_code = 0
    payload = {}
    for t in targets:
        findings = validate(plist, target=t, min_os=args.min_os)
        payload[t] = {
            "errors": findings.by("error"), "warnings": findings.by("warning"), "info": findings.by("info"),
            "summary": {"errorCount": len(findings.by("error")), "warningCount": len(findings.by("warning")),
                        "infoCount": len(findings.by("info")), "target": t, "minOS": args.min_os},
        }
        if findings.by("error") or (args.fail_on_warning and findings.by("warning")):
            exit_code = 1
    if args.json:
        print(json.dumps(payload[targets[0]] if len(targets) == 1 else payload, indent=2))
    else:
        for t in targets:
            findings = validate(plist, target=t, min_os=args.min_os)
            print(format_human(findings, args.file, t, args.min_os))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
