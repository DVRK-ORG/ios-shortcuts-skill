# Demo walkthrough: broken -> diagnosed -> fixed

This is the skill's flagship debugging demo. A realistic shortcut — *lowercase the clipboard, strip a leading `posted:` marker, and send the result* — ships with six planted bugs. We diagnose it without opening Shortcuts.app, fix the design-level bugs in the spec, and rebuild it clean.

Everything here runs on any OS. Only the final signing step needs a Mac.

---

## 1. The broken shortcut

Spec: [`examples/broken-post-clipboard.json`](../examples/broken-post-clipboard.json)  
Built fixture: `examples/broken-post-clipboard.shortcut` (regenerate with `py scripts/make_fixture.py` — it uses a fixed UUID seed, so the rebuilt file is byte-identical to the committed one)

```bash
py scripts/inspect_shortcut.py examples/broken-post-clipboard.shortcut
```

```
name:            Broken Post Clipboard
actions: 7
----------------------------------------------------------------------
  0. getclipboard  [as=clip]
  1. runshellscript  [as=lower]
      WFScript = 'printf \'%s\' "$1" | tr \'[:upper:]\' \'[:lower:]\''
  2. conditional  [mode=0, group=g1...]
      WFCondition = 99
  3. gettext  [as=draft]
      WFTextActionText = "<clip>"
  4. text.replace  [as=body]
      WFReplaceTextFind = '^posted\\s*:?\\s*'
      WFReplaceTextRegularExpression = True
      WFReplaceTextReplace = ''
      text = 'placeholder'
  5. math  [as=math]
      WFMathOperand = '10'
      WFMathOperation = '/'
  6. setclipboard
      WFInput = <clip>
```

Read that list once and the shape of the trouble is already visible: a shell script on what is meant to be an iPhone shortcut, an `If` with no input, a Replace Text carrying another action's key, an ASCII division sign, and no `End If` anywhere.

## 2. Diagnose: lint both targets and diff

```bash
py scripts/validate_shortcut.py examples/broken-post-clipboard.shortcut --target ios   --min-os 26
py scripts/validate_shortcut.py examples/broken-post-clipboard.shortcut --target macos --min-os 26
```

| Code | iOS | macOS | Meaning |
|---|:---:|:---:|---|
| `E_MACOS_ONLY` | **error** | — | `runshellscript` does not exist on iPhone/iPad |
| `E_COND_NO_INPUT` | error | error | `If` (mode 0) has no `WFInput` — nothing is being tested |
| `E_COND_LITERAL` | error | error | Condition `99` (contains) requires `WFConditionalActionString` |
| `E_INPUT_KEY` | error | error | `text.replace` carries `text`, a key that belongs to `text.changecase` |
| `E_MATH_OP` | error | error | `WFMathOperation` is ASCII `/`; Shortcuts expects `÷` (U+00F7) |
| `E_UNCLOSED_GROUP` | error | error | Group `g1` opens at action[2] and never closes |

**Result: iOS = 6 errors, macOS = 5 errors.**

That one-row difference is the whole point of the target-diff: `E_MACOS_ONLY` appears only in the iOS run, so *that* bug is platform-specific by definition. The other five fail everywhere — they are design bugs, not platform bugs. You get that split in seconds, without reading a single action by hand.

Warnings worth noting: `W_ICON_COLOR` (icon has a glyph but no colour) and `W_NO_VISIBLE_OUTPUT` (the shortcut ends on `setclipboard`, so a successful run shows the user nothing).

Machine-readable form for agents and CI:

```bash
py scripts/validate_shortcut.py examples/broken-post-clipboard.shortcut --target both --min-os 26 --json
```

## 3. Try the safe fixer — and watch it refuse

```bash
py scripts/fix_shortcut.py examples/broken-post-clipboard.shortcut -o fixed-attempt.shortcut
```

```
target ios: before 6E/3W -> after 5E/2W

Refusing to write: 5 error(s) need a design fix, machine repair cannot guess them:
  [E_MACOS_ONLY] ...
  [E_COND_NO_INPUT] ...
  [E_COND_LITERAL] ...
  [E_INPUT_KEY] ...
  [E_UNCLOSED_GROUP] ...
```

The fixer repaired the two things it can *prove* are mechanical — the ASCII `/` became `÷`, and the missing icon colour was filled — then stopped. It will not guess which variable the `If` should test, which action should replace a shell script, or where the missing `End If` belongs. **A fixer that guesses is how broken shortcuts get shipped with confidence.** Exit code `1`, no file written.

## 4. Fix the design in the spec

The corrected twin is [`examples/post-clipboard.json`](../examples/post-clipboard.json). Bug by bug:

| Bug | Fix |
|---|---|
| `runshellscript` lowercases via `tr` (macOS only) | Built-in `changecase` action — works on iOS, no "Allow Running Scripts" needed |
| `If` tests nothing, condition `99` has no literal | Test the cleaned body with condition `100` (has any value) — an existence check needs no literal at all |
| Replace Text uses the `text` key | The builder wires `WFInput` for `replace` automatically |
| ASCII `/` in a stray math action | Removed — it was dead weight, not a repair target |
| Group `g1` never closes | Matching `else` + `endif` on the same group |
| Ends silently on the clipboard | Success branch ends with Show Content; empty branch shows an alert |

The guard also changes the *behaviour*, not just the structure: an empty clipboard now produces "Nothing to post" instead of sending an empty message.

## 5. Rebuild and verify

```bash
py scripts/build_shortcut.py examples/post-clipboard.json -o "output/Post Clipboard.shortcut"
py scripts/validate_shortcut.py "output/Post Clipboard.shortcut" --target ios --min-os 26
py scripts/inspect_shortcut.py "output/Post Clipboard.shortcut"
```

```
0 error(s), 0 warning(s), 7 info
PASSED: no errors
```

```
  0. comment
  1. getclipboard  [as=clip]
  2. text.changecase  [as=lower]
      text = <clip>
  3. text.replace  [as=body]
      WFInput = <lower>
  4. conditional  [mode=0, group=g1...]
      WFCondition = 100
      WFInput = { Type: 'Variable', Variable: <body> }
  5. sendmessage
  6. showresult
  7. conditional  [mode=1, group=g1...]
  8. alert
  9. conditional  [mode=2, group=g1...]
```

Same intent, zero errors on both targets, and the control flow visibly opens, branches, and closes. (The remaining `info` findings are unused-output notes — comments and branch markers produce output nothing references, which is expected.)

## 6. Ship it

On a Mac:

```bash
shortcuts sign --mode anyone --input "Post Clipboard.shortcut" --output "Post Clipboard signed.shortcut"
```

Then AirDrop the signed file to the iPhone, or import it on the device and share an iCloud link. Before the first real send: replace the placeholder recipient `+15555550100` in the spec, rebuild, re-lint, and run once with known clipboard text to grant permissions.

No Mac? Deliver the spec plus this walkthrough as a numbered build recipe — every action above maps 1:1 to a Shortcuts.app action. Do not promise an importable file: iOS 15+ imports signed files only, and only macOS can sign.

---

**The lesson in one line:** lint both targets first, let the diff sort platform bugs from design bugs, fix design in the spec, and never let a tool write a "fixed" file it cannot prove is clean.
