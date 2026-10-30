"""shortcut_lib.py — shared helpers for building and reading Apple Shortcuts files.

An unsigned .shortcut file is a property list whose root dict describes a WFWorkflow:
top-level keys (WFWorkflowActions, WFWorkflowName, WFWorkflowIcon, ...) plus an ordered
WFWorkflowActions array. Each action is:

    {"WFWorkflowActionIdentifier": "is.workflow.actions.<name>",
     "WFWorkflowActionParameters": {"UUID": "<UPPERCASE-UUID>", ...params...}}

Zero dependencies: Python 3 stdlib only (plistlib, uuid, re).
See references/file-format.md for the full anatomy.
"""
from __future__ import annotations

import plistlib
import re
import uuid

PLACEHOLDER = "\ufffc"  # U+FFFC OBJECT REPLACEMENT CHARACTER — attachment marker inside token strings
A = "is.workflow.actions."

# Deterministic UUID mode state — see set_uuid_seed() below.
_UUID_SEED = None
_UUID_COUNTER = 0


def new_uuid() -> str:
    global _UUID_COUNTER
    if _UUID_SEED is not None:
        _UUID_COUNTER += 1
        return str(uuid.uuid5(uuid.UUID(_UUID_SEED), "action-%d" % _UUID_COUNTER)).upper()
    return str(uuid.uuid4()).upper()


def set_uuid_seed(seed):
    """Enable deterministic UUID generation. Pass None to return to random UUIDs.

    Deterministic mode keeps committed demo fixtures byte-stable across rebuilds,
    so regenerating one never dirties the repository.
    """
    global _UUID_SEED, _UUID_COUNTER
    _UUID_SEED = seed
    _UUID_COUNTER = 0


def utf16_len(s: str) -> int:
    """Length in UTF-16 code units — attachmentsByRange offsets are UTF-16 based, not Python chars."""
    return len(s.encode("utf-16-le")) // 2


def action_output_ref(out_uuid: str, name: str) -> dict:
    return {"Type": "ActionOutput", "OutputUUID": out_uuid, "OutputName": name}


def attachment(ref: dict) -> dict:
    return {"Value": ref, "WFSerializationType": "WFTextTokenAttachment"}


def variable_ref(var_name: str) -> dict:
    return attachment({"Type": "Variable", "VariableName": var_name})


def extension_input() -> dict:
    """Shortcut Input (share-sheet input) reference."""
    return attachment({"Type": "ExtensionInput"})


def conditional_input(ref: dict) -> dict:
    """The {Type: Variable, Variable: <token attachment>} wrapper an If expects."""
    return {"Type": "Variable", "Variable": attachment(ref)}


_REF_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def token_string(text: str, refs: dict) -> dict:
    """Build a WFTextTokenString plist value from text containing {name} placeholders.

    refs maps name -> attachment dict (e.g. action_output_ref(...)). Each placeholder
    becomes one U+FFFC char and gets an attachmentsByRange entry "{utf16_offset, 1}".
    """
    attachments = {}
    parts = []
    pos = 0
    last = 0
    for m in _REF_RE.finditer(text):
        literal = text[last:m.start()]
        parts.append(literal)
        pos += utf16_len(literal)
        name = m.group(1)
        if name not in refs:
            raise ValueError("unknown placeholder %s in text: %r" % (m.group(0), text))
        parts.append(PLACEHOLDER)
        attachments["{%d, 1}" % pos] = refs[name]
        pos += 1  # U+FFFC is in the BMP: exactly one UTF-16 code unit
        last = m.end()
    parts.append(text[last:])
    return {
        "Value": {"string": "".join(parts), "attachmentsByRange": attachments},
        "WFSerializationType": "WFTextTokenString",
    }


def maybe_token_string(text, refs):
    """Plain string when there are no {placeholders}; otherwise a WFTextTokenString.
    token_string raises on unknown names, so a typo'd {ref} fails the build loudly
    instead of silently shipping literal braces to the device."""
    if isinstance(text, str) and _REF_RE.search(text):
        return token_string(text, refs or {})
    return text


class ShortcutBuilder:
    """Assembles the WFWorkflow dict and serializes it to a .shortcut plist."""

    def __init__(
        self,
        name,
        client_version="2700.0.4",
        minimum_client_version=900,
        icon=None,
        types=None,
        input_classes=None,
        output_classes=None,
        has_output_fallback=False,
        has_input_variables=False,
    ):
        self.name = name
        self.client_version = client_version
        self.minimum_client_version = minimum_client_version
        # Widely used defaults: SF Symbol glyph + start color as ints.
        self.icon = icon or {"WFWorkflowIconGlyphNumber": 61440, "WFWorkflowIconStartColor": 431817727}
        self.types = types if types is not None else []
        self.input_classes = input_classes if input_classes is not None else ["WFStringContentItem"]
        self.output_classes = output_classes if output_classes is not None else []
        self.has_output_fallback = has_output_fallback
        self.has_input_variables = has_input_variables
        self.actions = []
        self.refs = {}  # 'as' name -> attachment dict for {name} placeholders in text

    # ------------------------------------------------------------------ low level
    def raw(self, identifier, parameters=None, as_name=None, uuid_value=None):
        params = {"UUID": uuid_value or new_uuid()}
        if as_name:
            params["CustomOutputName"] = as_name
            self.refs[as_name] = action_output_ref(params["UUID"], as_name)
        if parameters:
            params.update(parameters)
        self.actions.append(
            {"WFWorkflowActionIdentifier": identifier, "WFWorkflowActionParameters": params}
        )
        return params["UUID"]

    def _input(self, spec):
        """Resolve an 'input' spec:
        '{name}' (whole value) -> attachment to a named action output,
        '$input' / '{input}' -> Shortcut Input, '$var:Name' -> variable attachment,
        text containing {placeholders} -> WFTextTokenString, plain text -> raw string,
        dict -> passthrough, None -> omit the parameter."""
        if spec is None:
            return None
        if isinstance(spec, dict):
            return spec
        if spec == "$input":
            return extension_input()
        if spec.startswith("$var:"):
            return variable_ref(spec[5:])
        if isinstance(spec, str):
            m = _REF_RE.fullmatch(spec.strip())
            if m:
                name = m.group(1)
                if name == "input":
                    return extension_input()
                if name not in self.refs:
                    raise ValueError("unknown input reference %r (no earlier action with as=%r)" % (spec, name))
                return attachment(self.refs[name])
            if _REF_RE.search(spec):
                return self._text(spec)  # mixed text + references -> WFTextTokenString
            return spec
        raise ValueError("bad input spec: %r" % (spec,))

    def _text(self, text):
        return maybe_token_string(text, self.refs)

    # ------------------------------------------------------------- convenience actions
    def text(self, text, as_name=None):
        return self.raw(A + "gettext", {"WFTextActionText": self._text(text)}, as_name)

    def comment(self, text):
        return self.raw(A + "comment", {"WFCommentActionText": text})

    def show(self, text, as_name=None):
        return self.raw(A + "showresult", {"Text": self._text(text)}, as_name)

    def alert(self, title, message):
        return self.raw(
            A + "alert",
            {"WFAlertActionTitle": title, "WFAlertActionMessage": self._text(message)},
        )

    def notify(self, body, title=None, sound=True):
        p = {"WFNotificationActionBody": self._text(body), "WFNotificationActionSound": bool(sound)}
        if title:
            p["WFNotificationActionTitle"] = title
        return self.raw(A + "notification", p)

    def ask(self, prompt, input_type="Text", as_name=None):
        return self.raw(
            A + "ask", {"WFAskActionPrompt": prompt, "WFInputType": input_type}, as_name
        )

    def set_variable(self, name, input_spec=None):
        p = {"WFVariableName": name}
        inp = self._input(input_spec)
        if inp is not None:
            p["WFInput"] = inp
        return self.raw(A + "setvariable", p)

    def get_variable(self, name, as_name=None):
        return self.raw(A + "getvariable", {"WFVariableName": name}, as_name or name)

    def url(self, text, as_name=None):
        return self.raw(A + "url", {"WFURLActionURL": self._text(text)}, as_name)

    def open_url(self, text):
        return self.raw(A + "openurl", {"WFURL": self._text(text)})

    def download(self, url_text, method="GET", as_name=None, extra=None):
        p = {"WFURL": self._text(url_text), "WFHTTPMethod": method}
        if extra:
            p.update(extra)
        return self.raw(A + "downloadurl", p, as_name)

    def quicklook(self):
        return self.raw(A + "quicklook", {})

    def wait(self, seconds):
        # Number-typed parameters are commonly stored as strings by Shortcuts.app.
        return self.raw(A + "delay", {"WFDelayTime": str(seconds)})

    def get_dict_value(self, key, input_spec=None, as_name=None):
        p = {"WFDictionaryKey": key}
        inp = self._input(input_spec)
        if inp is not None:
            p["WFInput"] = inp
        return self.raw(A + "getvalueforkey", p, as_name)

    def get_clipboard(self, as_name="Clipboard"):
        return self.raw(A + "getclipboard", {}, as_name)

    def set_clipboard(self, input_spec):
        return self.raw(A + "setclipboard", {"WFInput": self._input(input_spec)})

    def detect_links(self, input_spec, as_name="URLs"):
        return self.raw(A + "detect.link", {"WFInput": self._input(input_spec)}, as_name)

    def get_first_item(self, input_spec, as_name="First Item"):
        return self.raw(
            A + "getitemfromlist",
            {"WFInput": self._input(input_spec), "WFItemSpecifier": "First Item"},
            as_name,
        )

    def change_case(self, input_spec, case="lowercase", as_name=None):
        # Change Case takes its input under the action-specific `text` key.
        return self.raw(A + "text.changecase", {"text": self._input(input_spec), "WFCaseType": case}, as_name)

    def replace_text(self, input_spec, find, replace="", case_sensitive=False, regex=False, as_name=None):
        p = {
            "WFInput": self._input(input_spec),
            "WFReplaceTextFind": find,
            "WFReplaceTextReplace": replace,
            "WFReplaceTextCaseSensitive": bool(case_sensitive),
            "WFReplaceTextRegularExpression": bool(regex),
        }
        return self.raw(A + "text.replace", p, as_name)

    def calculate(self, operation, operand, input_spec, as_name=None):
        # Addition omits WFMathOperation; * and / have already been translated
        # to × and ÷ by the spec layer.
        p = {"WFInput": self._input(input_spec), "WFMathOperand": str(operand)}
        if operation:
            p["WFMathOperation"] = operation
        return self.raw(A + "math", p, as_name)

    def send_message(self, content, recipients, show_when_run=False, as_name=None):
        return self.raw(
            A + "sendmessage",
            {
                "IntentAppIdentifier": "com.apple.MobileSMS",
                "WFSendMessageActionRecipients": recipients,
                "WFSendMessageContent": self._text(content),
                "ShowWhenRun": bool(show_when_run),
            },
            as_name,
        )

    # ------------------------------------------------------------------ control flow
    # Blocks are separate actions sharing a GroupingIdentifier UUID with an integer
    # WFControlFlowMode: 0 = open, 1 = middle branch (else / menu case), 2 = close.
    # WFCondition codes: 0-3 numeric <, <=, >, >=; 4 is, 5 is not, 8 begins with,
    # 9 ends with, 99 contains, 999 does not contain, 100/101 has/no value.
    def if_begin(self, input_spec=None, condition=100, compare=None, group=None):
        g = group or new_uuid()
        p = {"GroupingIdentifier": g, "WFControlFlowMode": 0, "WFCondition": condition}
        inp = self._input(input_spec)
        if inp is not None:
            # If inputs are wrapped as Variable -> token attachment in exports.
            p["WFInput"] = (
                conditional_input(inp["Value"])
                if isinstance(inp, dict) and inp.get("WFSerializationType") == "WFTextTokenAttachment"
                else inp
            )
        if compare is not None:
            if isinstance(compare, (int, float)) and not isinstance(compare, bool):
                p["WFNumberValue"] = compare
            else:
                p["WFConditionalActionString"] = self._text(compare)
        self.raw(A + "conditional", p)
        return g

    def otherwise(self, group):
        self.raw(A + "conditional", {"GroupingIdentifier": group, "WFControlFlowMode": 1})

    def if_end(self, group):
        self.raw(A + "conditional", {"GroupingIdentifier": group, "WFControlFlowMode": 2})

    def menu_begin(self, items, group=None):
        g = group or new_uuid()
        self.raw(
            A + "choosefrommenu",
            {"GroupingIdentifier": g, "WFControlFlowMode": 0, "WFMenuItems": list(items)},
        )
        return g

    def menu_case(self, title, group):
        self.raw(
            A + "choosefrommenu",
            {"GroupingIdentifier": group, "WFControlFlowMode": 1, "WFMenuItemTitle": title},
        )

    def menu_end(self, group):
        self.control_end(A + "choosefrommenu", group)

    def repeat_count_begin(self, count, group=None):
        g = group or new_uuid()
        self.raw(
            A + "repeat.count",
            {"GroupingIdentifier": g, "WFControlFlowMode": 0, "WFRepeatCount": str(count)},
        )
        return g

    def repeat_each_begin(self, group=None):
        g = group or new_uuid()
        self.raw(A + "repeat.each", {"GroupingIdentifier": g, "WFControlFlowMode": 0})
        return g

    def control_end(self, identifier, group):
        self.raw(identifier, {"GroupingIdentifier": group, "WFControlFlowMode": 2})

    # ------------------------------------------------------------------ serialization
    def to_plist(self) -> dict:
        return {
            "WFWorkflowActions": self.actions,
            "WFWorkflowClientVersion": self.client_version,
            "WFWorkflowHasOutputFallback": self.has_output_fallback,
            "WFWorkflowHasShortcutInputVariables": self.has_input_variables,
            "WFWorkflowIcon": self.icon,
            "WFWorkflowImportQuestions": [],
            "WFWorkflowInputContentItemClasses": self.input_classes,
            "WFWorkflowMinimumClientVersion": self.minimum_client_version,
            "WFWorkflowMinimumClientVersionString": str(self.minimum_client_version),
            "WFWorkflowName": self.name,
            "WFWorkflowOutputContentItemClasses": self.output_classes,
            "WFWorkflowTypes": self.types,
        }

    def dump(self, path, fmt=plistlib.FMT_BINARY):
        with open(path, "wb") as f:
            plistlib.dump(self.to_plist(), f, fmt=fmt)

    @staticmethod
    def load(path):
        """Load an unsigned .shortcut/.plist. Raises on signed AEA1 files."""
        with open(path, "rb") as f:
            head = f.read(8)
        if head[:4] == b"AEA1":
            raise ValueError(
                "signed Apple Encrypted Archive (AEA1) — get the unsigned plist first "
                "(see references/file-format.md, 'Getting the unsigned plist out of a signed file')"
            )
        with open(path, "rb") as f:
            return plistlib.load(f)
