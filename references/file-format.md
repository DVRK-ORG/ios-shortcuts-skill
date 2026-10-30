# Apple Shortcuts — file format & platform facts

Everything here is reverse-engineered or documented by Apple; the format itself
is **not** publicly specified by Apple. Treat it as a working reference, and
verify against a real export when something looks off.

## What a `.shortcut` file is

A property list (plist). Three flavours matter:

| Form | Magic | Notes |
|---|---|---|
| Unsigned binary | `bplist00` | Parse it with `scripts/inspect_shortcut.py`. |
| Unsigned XML | `<?xml` … `<plist>` | Also parseable; convert with `plutil -convert binary1` on a Mac. |
| **Signed** | `AEA1` | Apple Encrypted Archive. **Cannot be parsed or linted.** |

**Signed vs unsigned is the single most important deployment fact.**

- Since iOS 15, iOS **only imports signed** `.shortcut` files.
- **Only macOS can sign.** There is no way to sign on iOS or Windows.
- A signed file is an encrypted archive, so a signed `.shortcut` cannot be
  linted or diffed directly. To inspect one, open it in Shortcuts.app on a Mac
  and re-export (File → Export) to get a plain plist, or use the iCloud
  `downloadURL` trick below.

## Root dictionary keys

| Key | Type | Purpose |
|---|---|---|
| `WFWorkflowActions` | array of dict | **Required.** The ordered action list. |
| `WFWorkflowName` | string | Recommended. If missing, the **file name** becomes the shortcut name on import. |
| `WFWorkflowClientVersion` | int or string | Build number of the client that wrote it, e.g. `2773` or `"2700.0.4"`. |
| `WFWorkflowClientRelease` | string | e.g. `"2773"`. |
| `WFWorkflowMinimumClientVersion` | int | `900` = broad compat (iOS 14+). `1100`+ = iOS 15+ (implies signed-file import). |
| `WFWorkflowMinimumClientVersionString` | string | String form of the above. |
| `WFWorkflowIcon` | dict | `WFWorkflowIconGlyphNumber` + `WFWorkflowIconStartColor`. Both required for a custom icon. These are the **only** valid keys — a friendly key such as `glyph` or `color` is written verbatim by a naive builder, the shortcut imports with a generic icon, and nothing in the file says why. The spec builder accepts either form and normalises it; the linter reports unknown icon keys as `E_ICON_KEYS`. |
| `WFWorkflowInputContentItemClasses` | array | Accepted input types — legacy `WF*ContentItem` names or UTIs such as `public.plain-text`, `public.url`, `public.image`. |
| `WFWorkflowTypes` | array | Surfaces: `ActionExtension` (share sheet), `NCWidget`, `WatchKit`. `[]` = library only. |
| `WFQuickActionSurfaces` | array | Where it appears as a Quick Action. |
| `WFWorkflowImportQuestions` | array | Prompts shown on import: `{ActionIndex, Category:"Parameter", ParameterKey, Text, DefaultValue}` — the answer fills that action's parameter at add-time. |
| `WFWorkflowHasOutputFallback` | bool | `false` default. |
| `WFWorkflowHasShortcutInputVariables` | bool | `false` unless the shortcut declares input variables. |

Missing `WFWorkflowInputContentItemClasses` means the shortcut accepts nothing
useful — a common cause of "it does nothing when run from the Share Sheet".

## Action dictionary structure

```
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.<name>",
  "WFWorkflowActionParameters": {
    "UUID": "<UPPERCASE-UUID>",        // unique per action; outputs are referenced by it
    "CustomOutputName": "myVar",       // optional, friendly output name
    ...action-specific WF* parameter keys...
  }
}
```

- Third-party App Intents use their own bundle-style identifiers; those cannot
  be validated locally.
- `UUID` — **uppercase** 8-4-4-4-12 hex, unique per action, generated (not
  hand-picked). Repeating-hex placeholders like `AAAAAAAA-…` are rejected.
  The spec builder generates them randomly by default; pass `--seed <uuid>` to
  `build_shortcut.py` for a byte-reproducible build (same seed → same file).
- Parameter values are raw scalars (note Apple often stores number-typed params
  as *strings*, e.g. `"42"`), a variable/action-output reference, a token string,
  or a nested dict/list.

## Variable wiring — the hard part

Shortcuts has no explicit dataflow. A later action refers to an earlier
action's output by that action's `UUID`.

### 1. The source action

```
"UUID": "7F3A4E91-C2D8-4B56-BE5A-0242AC120002",
"CustomOutputName": "Clipboard"
```

### 2. The consumer — token attachment (whole value)

```
"WFInput": {
  "Value": { "Type": "ActionOutput", "OutputUUID": "7F3A…", "OutputName": "Clipboard" },
  "WFSerializationType": "WFTextTokenAttachment"
}
```

Other `Type` values: `Variable` (`VariableName`), `ExtensionInput` (the
shortcut's own input — never emit the legacy `is.workflow.actions.input`
action), `Ask`, `Clipboard`, `CurrentDate`, `DeviceDetails`, `CurrentApp`.

`ExtensionInput` works **anywhere** a value can be referenced, not just as a
whole-value input. Inside a text field it appears as an attachment inside the
token string, exactly like an action output:

```
"WFTextActionText": {
  "Value": {
    "string": "You said ￼",
    "attachmentsByRange": { "{9, 1}": { "Value": { "Type": "ExtensionInput" }, "WFSerializationType": "WFTextTokenAttachment" } }
  },
  "WFSerializationType": "WFTextTokenString"
}
```

The spec builder resolves the `{input}` placeholder to this automatically, in
text fields and in input fields alike.

### 3. The consumer — variable inside a string

Text with an embedded variable is a **token string**. The variable's position
is marked with U+FFFC (`￼`) and the exact UTF-16 offset is recorded in
`attachmentsByRange`:

```
"WFTextActionText": {
  "Value": {
    "string": "Clipboard: ￼",
    "attachmentsByRange": { "{11, 1}": { "Type": "ActionOutput", "OutputUUID": "7F3A…", "OutputName": "Clipboard" } }
  },
  "WFSerializationType": "WFTextTokenString"
}
```

Rules that matter:

- The range key format is `{position, length}` — position in **UTF-16 code
  units** (an emoji before the placeholder counts as 2), length always `1`.
- The count of `attachmentsByRange` entries must equal the count of U+FFFC
  characters, and every offset must land exactly on one. Off by one imports
  fine and then produces garbage.
- Never strip or normalise the U+FFFC character. It is invisible in most
  editors but load-bearing.
- `WFURL`-family parameters (URL, Get Contents of URL, Open URL) use the
  token-string form too, even when the URL is fully static.

**Order matters.** A reference must point at an action that has *already run*.
Pointing at a later action is a silent failure: the file imports cleanly and
the field is simply empty at runtime. The linter flags this as `W_FORWARD_REF`.

## Control flow

Control flow is encoded by **separate actions** sharing a `GroupingIdentifier`
UUID, with an **integer** `WFControlFlowMode`: `0` = open, `1` = middle branch
(else / menu case), `2` = close. The closing action must use the **same action
identifier** as the opening one.

```
If:          is.workflow.actions.conditional   mode 0 (+ WFCondition, WFInput, literal), 1 = Otherwise, 2 = End If
Menu:        is.workflow.actions.choosefrommenu mode 0 (+ WFMenuItems: [titles]); each case mode 1 (+ WFMenuItemTitle); end mode 2
Repeat N:    is.workflow.actions.repeat.count   mode 0 (+ WFRepeatCount), end mode 2
Repeat each: is.workflow.actions.repeat.each    mode 0, end mode 2 (loop item flows as the block's input)
```

- A plain Otherwise is mode `1` with no condition fields. An **Otherwise If**
  (OS 27+) is mode `1` *with* condition fields.
- Every condition needs an explicit `WFInput`; there is no implicit-input mode.
  In exports the value is often wrapped as `{Type:"Variable", Variable:{…token
  attachment…}}` — the bundled builder emits that wrapper for If inputs.
- **Multi-condition If** ("Any/All are true") uses a `WFConditions` key with
  `WFSerializationType = WFContentPredicateTableTemplate`. Never mix it with
  top-level `WFCondition` + `WFInput` on the same If.

### `WFCondition` codes — read this twice

`WFCondition` is an **integer operator code**, not a name. String names like
`"Equals"` may import but degrade at runtime.

| Code | Meaning | Required literal field |
|---|---|---|
| `0` | is less than | `WFNumberValue` |
| `1` | is less than or equal to | `WFNumberValue` |
| `2` | is greater than | `WFNumberValue` |
| `3` | is greater than or equal to | `WFNumberValue` |
| `4` | is (string equals) | `WFConditionalActionString` |
| `5` | is not (string) | `WFConditionalActionString` |
| `8` | begins with | `WFConditionalActionString` |
| `9` | ends with | `WFConditionalActionString` |
| `99` | contains | `WFConditionalActionString` |
| `999` | does not contain | `WFConditionalActionString` |
| `100` | has any value | none |
| `101` | does not have any value | none |
| `1002` | is today (dates) | — |
| `1003` | is between | `WFNumberValue` (lower) + `WFAnotherNumber` (upper) |

Code `0` is **is less than**, not "equals" — the most common misreading, and
the reason an If that "should obviously match" never fires.

### Repeat / Choose from Menu notes

- `repeat.each` takes `WFInput` pointing at the list. Inside the loop use
  **Repeat Item**, not Repeat Results; list indexes are **1-based**.
- `choosefrommenu` items are a plain string array in `WFMenuItems`; each case
  block carries its title in `WFMenuItemTitle`.

## Action input keys — the silent-failure trap

Different actions use different parameter keys for their input. Using the
wrong key **imports cleanly but shows an empty field in the editor**, and
produces no result at runtime. This is the most common silent failure, and the
linter's `E_INPUT_KEY` exists for it.

| Action | Identifier | Main input/value key |
|---|---|---|
| Text | `is.workflow.actions.gettext` | `WFTextActionText` — **never** `is.workflow.actions.text` |
| Comment | `is.workflow.actions.comment` | `WFCommentActionText` |
| Show Content (iOS 26 name; was Show Result) | `is.workflow.actions.showresult` | `Text` |
| Quick Look | `is.workflow.actions.quicklook` | none — shows its input; the debugging workhorse |
| Show Alert | `is.workflow.actions.alert` | `WFAlertActionTitle`, `WFAlertActionMessage` |
| Show Notification | `is.workflow.actions.notification` | `WFNotificationActionBody`, `WFNotificationActionTitle`, `WFNotificationActionSound` |
| Ask for Input | `is.workflow.actions.ask` | `WFAskActionPrompt`, `WFInputType` |
| Replace Text | `is.workflow.actions.text.replace` | `WFInput` |
| Change Case / Split / Combine Text | `…text.changecase` / `.text.split` / `.text.combine` | `text` |
| Set Variable | `is.workflow.actions.setvariable` | `WFVariableName`, `WFInput` |
| Get Variable | `is.workflow.actions.getvariable` | `WFVariableName` |
| Get Dictionary Value | `is.workflow.actions.getvalueforkey` | `WFDictionaryKey` (dot paths, **1-based** indexes: `artists.1.name`), `WFInput` |
| Detect Dictionary (JSON → dictionary) | `is.workflow.actions.detectdictionary` | `WFInput` |
| URL | `is.workflow.actions.url` | `WFURLActionURL` |
| Open URL | `is.workflow.actions.openurl` | `WFURL` or `WFInput` (both appear in real exports) |
| Get Contents of URL | `is.workflow.actions.downloadurl` | `WFURL`, `WFHTTPMethod`, `WFHTTPHeaders`, `WFHTTPBody`, `ShowHeaders` |
| Get Clipboard | `is.workflow.actions.getclipboard` | none |
| Copy to Clipboard | `is.workflow.actions.setclipboard` | `WFInput` |
| Save File | `is.workflow.actions.documentpicker.save` | `WFInput` |
| Run Shortcut | `is.workflow.actions.runworkflow` | `WFWorkflowName`, `WFInput` |
| Wait | `is.workflow.actions.delay` | `WFDelayTime` (string-typed seconds, e.g. `"1"`) |
| Math | `is.workflow.actions.math` | `WFMathOperand` |
| Base64 Encode | `is.workflow.actions.base64encode` | `WFInput` |
| Run Shell Script (macOS) | `is.workflow.actions.runshellscript` | `WFScript` |

`WFInput` is the generic variable-picker key — many actions accept it, so
seeing `WFInput` on an action is not by itself a mistake. The dangerous case
is a *specific* key belonging to a different action, e.g. `text` on Replace
Text. When you need keys not listed here, use the **skeleton trick**: build the
action once in Shortcuts.app, dump it with `scripts/inspect_shortcut.py`, and
copy the exact identifier + parameter dict into your spec as `{"do": "raw", …}`.
Never guess parameter keys.

## Math operators

`is.workflow.actions.math` — `WFMathOperation`:

| Operation | Value | Note |
|---|---|---|
| Addition | *omit the key entirely* | No key means addition. |
| Subtraction | `-` (U+002D) | ASCII hyphen. |
| Multiplication | `×` (U+00D7) | **Never** `*`. |
| Division | `÷` (U+00F7) | **Never** `/` — Shortcuts silently renders ASCII `/` as `+`. |

`WFMathOperand` must be a **plain literal string** like `"10"`, not a wrapped
dict. Scientific operations use `WFMathOperation` = `…` (U+2026) with the real
operator in `WFScientificMathOperation`.

## Platform gating

| Identifier | Availability |
|---|---|
| `is.workflow.actions.runshellscript` | **macOS only** |
| `is.workflow.actions.runapplescript` | **macOS only** |
| `is.workflow.actions.runjavascriptforautomation` | **macOS only** |
| `is.workflow.actions.runsshscript` | iOS (needs an SSH host) |
| `is.workflow.actions.runjavascriptonwebpage` | iOS (Safari only) |
| `is.workflow.actions.askllm` (Use Model) | iOS/macOS 26+ **and** Apple Intelligence hardware (iPhone 15 Pro+, M-series) |
| `is.workflow.actions.getstoredcontent` / `setstoredcontent` / `deletestoredcontent` / `additemtolist` | OS 27+ |
| HealthKit actions (`filter.health.*`) | iOS/iPadOS only |

Scripting actions need Settings → Shortcuts → Advanced → **Allow Running
Scripts** on the device.

## OS 26 / 27 changes that bite

**iOS 26 / macOS 26**
- "Show Result" was **renamed to "Show Content"**. The identifier stayed
  `is.workflow.actions.showresult`, so old files keep working — but searching
  the action list for "Show Result" may come up empty.
- 25+ new actions, mostly Apple Intelligence: Use Model (`askllm`), Summarize
  Text, Rewrite Text, Proofread Text, Create Image, and friends.
- Mac gained personal automations.

**iOS 27**
- **Automations are built directly into shortcuts** and sync between devices.
  The separate Automation tab is gone.
- New storage actions keep state across runs (iCloud-synced, shared between
  shortcuts).
- "If" gained "Otherwise If"; new triggers (notification received, screenshot
  saved, workout started…).
- "Describe a Shortcut" — natural-language shortcut creation (Apple
  Intelligence). Useful for a first draft; the output still needs linting.

## Other verified details

- **Dictionary dot notation** uses 1-based indexes: `results.tracks.items`,
  `artists.1.name`. Guard optional parents before dereferencing — a missing
  key returns empty, not an error.
- Run `detectdictionary` on an API response before `getvalueforkey`.
- **Sunrise/sunset** from Daily forecasts are lists — insert **Get Item from
  List** (First/Last Item) before Format Date.
- **Never inject raw Dictionary/List outputs into JSON text templates** — they
  stringify as newline-separated blocks, not valid JSON.
- **JSON request bodies**: for `WFHTTPBodyType = JSON`, use `WFJSONValues`
  for flat key/value payloads so the body survives in the UI.
- **OS 27 boolean toggles** must be real plist booleans, not strings:
  `ignoreWhitespace`, `interpretAsMarkdown`, `WFAllowWebSearch`, and friends.
- **Comments**: `is.workflow.actions.comment` with `WFCommentActionText`.
  Comment text should be plain human language — never plist jargon or UUIDs.
- Content-item classes: legacy names (`WFStringContentItem`, `WFURLContentItem`,
  `WFImageContentItem`, `WFGenericFileContentItem`, `WFContactContentItem`) and
  UTIs (`public.plain-text`, `public.url`, `public.image`) both appear in real
  files; be consistent within one shortcut.

## Getting the unsigned plist out of a signed (AEA1) file

The AEA1 payload is encrypted; you cannot parse it directly. Options:

- **Mac**: import into Shortcuts.app, or read the shortcut from
  `~/Library/Shortcuts/Shortcuts.sqlite` — the `ZDATA` column is a binary plist
  holding the action list (a *list* of action dicts, not the top-level dict).
- **iCloud link**: for `https://www.icloud.com/shortcuts/<id>`, the web API
  field `fields.shortcut.value.downloadURL` serves the **unsigned** plist.
- **iOS ≤ 14 device**: the "Get My Shortcuts" action exports unsigned files.
- Or just rebuild from a spec with `scripts/build_shortcut.py`.

## Sources

- Apple User Guide — Shortcuts for iPhone/iPad/Mac (URL schemes, sharing, CLI).
- `shortcuts(1)` man page and Apple Support "Run shortcuts from the command
  line" — CLI and signing semantics.
- Apple Support "What's new in Shortcuts for iOS 26 / 27" — action and
  automation changes.
- sebj/iOS-Shortcuts-Reference — canonical key reference.
- Community reverse-engineering: `shortcuts-js`, `shortcutkit`,
  `clean-shortcuts`, `shortcut-source-saver`, `shortcuts-playground-plugin` —
  plist structure, operator codes, and modern action catalogs.
