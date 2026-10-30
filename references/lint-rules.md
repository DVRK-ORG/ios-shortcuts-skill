# Linter rule reference

```
py scripts/validate_shortcut.py <file.shortcut> [--target ios|macos|both] [--min-os N] [--json] [--fail-on-warning]
```

Exit code `1` if any error is present (warnings too, with
`--fail-on-warning`). `--json` emits machine-readable findings with stable
codes. Errors block shipping; warnings need a human decision. The rule suite is
proven by `scripts/test_lint.py` (`py scripts/test_lint.py`).

## Errors — fix before shipping

| Code | Meaning | Typical fix |
|---|---|---|
| `E_ROOT` | Root is not a dictionary | Not a Shortcuts workflow plist |
| `E_NO_ACTIONS` | No `WFWorkflowActions` array | Rebuild the file |
| `E_BAD_ACTION` | An action entry is not a dict | Rebuild that action |
| `E_BAD_PARAMS` | `WFWorkflowActionParameters` is not a dict | Rebuild that action |
| `E_NO_IDENTIFIER` | Action missing `WFWorkflowActionIdentifier` | Add it |
| `E_BAD_UUID` | UUID not uppercase 8-4-4-4-12 hex | Generate a real uppercase UUID |
| `E_PLACEHOLDER_UUID` | UUID is repeating hex (`AAAAAAAA-…`) | Generate a real UUID |
| `E_DUPLICATE_UUID` | Two actions share a UUID | Regenerate one |
| `E_MACOS_ONLY` | macOS-only action on an iOS target | Replace with a built-in action, or make it a Mac-only shortcut |
| `E_OS27_ACTION` | OS 27 action on an older target | Raise the minimum OS, or use an older equivalent |
| `E_MODE_TYPE` | `WFControlFlowMode` is a string | Use an integer (`0`/`1`/`2`) |
| `E_GROUPING_ID` | Control-flow action missing/empty `GroupingIdentifier` | Set a UUID string shared by the block |
| `E_UNCLOSED_GROUP` | Control-flow block never closes | Add the matching end action (mode 2, same `GroupingIdentifier`) |
| `E_ORPHAN_END` | End action with no opener | Remove it or restore the opener |
| `E_GROUP_ID_MISMATCH` | End-block identifier differs from the opener's | Reuse the opener's identifier for mode 2 |
| `E_COND_NO_INPUT` | If action has no `WFInput` | Wire the variable being tested |
| `E_COND_LITERAL` | Condition code needs a literal field that is missing | Add `WFConditionalActionString` (string codes) or `WFNumberValue` (numeric codes) |
| `E_INPUT_KEY` | Action has another action's specific input key | Use the key from the table in `file-format.md` |
| `E_MATH_OP` | `WFMathOperation` is ASCII `*` or `/` | Use `×` (U+00D7) or `÷` (U+00F7) |
| `E_EMPTY_LOCATION` | Location parameter blank | Wire a real location output |
| `E_TOKEN_RANGE` | Attachment offsets do not line up with the U+FFFC placeholders | Recompute offsets (UTF-16 code units, length 1) |
| `E_DANGLING_REF` | Reference to an `OutputUUID` no action declares | Fix the UUID or add the missing action |

Machine-repairable by `scripts/fix_shortcut.py`: `E_MATH_OP`, parseable
`E_TOKEN_RANGE`, `W_ICON_COLOR`. Everything else needs a design decision.

## Warnings — judge each one

| Code | Meaning |
|---|---|
| `W_EMPTY` | The shortcut has zero actions |
| `W_NO_NAME` | No `WFWorkflowName` — the file name becomes the shortcut name |
| `W_NO_CLIENT_VERSION` | No `WFWorkflowClientVersion`/`Release` |
| `W_NO_ICON` / `W_ICON_GLYPH` / `W_ICON_COLOR` | Icon missing or incomplete — generic icon |
| `W_TYPES_SHAPE` / `W_SURFACES_SHAPE` | `WFWorkflowTypes`/`WFQuickActionSurfaces` is not an array |
| `W_NO_PARAMS` | Action has no parameters dictionary |
| `W_FOREIGN_IDENTIFIER` | Not an `is.workflow.actions.*` id — third-party App Intent, cannot be validated |
| `W_LEGACY_INPUT` | Legacy `is.workflow.actions.input` — prefer an `ExtensionInput` attachment |
| `W_AI_DEVICE` | Apple Intelligence action — needs iPhone 15 Pro or later |
| `W_CONDITION_STRING` | `WFCondition` is a name string — use the integer code |
| `W_UNKNOWN_CONDITION` | Undocumented condition code |
| `W_COND_EXTRA_LITERAL` | Existence condition with a literal set (harmless but wrong) |
| `W_MIXED_CONDITIONS` | Both `WFConditions` and `WFCondition` present — pick one pattern (reported as a warning; some exports mix harmlessly) |
| `W_MATH_OPERAND` | `WFMathOperand` wrapped in a dict instead of a plain literal |
| `W_NO_INPUT` | Action has no input wired and no `CustomOutputName` |
| `W_EMPTY_FIELD` | A required text parameter is an empty string |
| `W_TOKEN_NO_ATTACH` | Token string contains U+FFFC but `attachmentsByRange` is empty |
| `W_FORWARD_REF` | References an action that runs **later** — the value will be empty |
| `W_NO_VISIBLE_OUTPUT` | The shortcut ends on a data action, so running it shows the user nothing |
| `W_GROUP_MULTI` | More than one opener in a control-flow group |

## Info — no action needed

| Code | Meaning |
|---|---|
| `I_NO_INPUT_CLASSES` | No `WFWorkflowInputContentItemClasses` — accepts no useful input |
| `I_SIGNED_IMPORT` | Minimum client version implies iOS 15+ signed-file import |
| `I_UNUSED_OUTPUT` | An action's output is referenced by nothing (often fine — e.g. comments) |

## The target-diff diagnostic

When a shortcut "works on my Mac but not on my iPhone", lint it twice and
compare:

```bash
py scripts/validate_shortcut.py <file.shortcut> --target macos --min-os 26
py scripts/validate_shortcut.py <file.shortcut> --target ios   --min-os 26
```

Errors that appear **only in the iOS run** are platform bugs by definition —
a macOS-only action, an OS-gated action, or a permission that only exists on
one platform. The diff *is* the diagnosis, and it is faster than reading every
action by hand.

Same trick for version gating: `--min-os 26` vs `--min-os 27` isolates
actions that need the newer OS.

## False positives to be aware of

- **`W_NO_INPUT` on an Otherwise branch** — a plain Otherwise (mode 1) carries
  no condition by design. The linter skips control-flow markers; if you see
  this on a mode-1 action, it is a bug in the linter.
- **`W_FORWARD_REF`** fires on any reference to a later action. It is a
  genuine runtime problem, but it is reported as a warning because an
  occasionally-valid pattern exists (referencing an action inside a branch
  that ran in a previous iteration). Confirm before treating it as fatal.
- **`E_INPUT_KEY`** only fires for keys specific to a different action.
  `WFInput` is generic and is never flagged.
- **`W_CONDITION_STRING`** — older exports genuinely use names like
  `"Equals"`. They may work. Converting to the integer code is still better.
- **`W_NO_VISIBLE_OUTPUT`** fires when the last action is not a user-visible
  output. That is correct for a shortcut whose output is consumed by another
  shortcut — but if the user runs it directly, add a Show Content / Show Alert
  at the end.
- **`W_NO_VISIBLE_OUTPUT`** does not fire when the last action is a
  control-flow end (mode 2), since the real output sits inside the block.
