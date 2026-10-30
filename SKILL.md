---
name: ios-shortcuts
description: >-
  Build, inspect, lint, debug, and ship Apple Shortcuts automations (.shortcut files)
  for iPhone, iPad, Mac, and Watch from any AI agent, on any OS — including Windows.
  Use when the user wants to create an iOS/macOS shortcut or automation, install,
  sign or share a .shortcut file, inspect or reverse-engineer an existing one, work
  out why a shortcut does not run / fails / returns empty / cannot be added /
  does not appear in the Share Sheet, wire variables and If-conditions correctly,
  or improve an existing shortcut — even if they never say "plist" or "skill" and
  just say "make a shortcut that...". Triggers on: "make a shortcut", "shortcut not
  running", "couldn't add shortcut", "deploy to iPhone", "iOS automation",
  "share sheet shortcut", "sign a .shortcut", "shortcuts CLI", "Siri automation",
  "shortcut returns empty".
disable-model-invocation: false
license: MIT
compatibility: Python 3.9+ standard library only; no third-party packages. macOS-only for signing (shortcuts sign) and on-device GUI import.
metadata:
  version: "1.0.0"
  author: "By DVRRK (DVRK-ORG)"
  format: "Agent Skills (SKILL.md)"
---

# iOS Shortcuts — build, lint, debug, ship

Ship working Apple Shortcuts: author the plist from a JSON spec, lint it before it
reaches a device, sign and deliver it, and debug what breaks. A `.shortcut` file is
just a property list — you can build and verify one anywhere, including Windows,
with zero dependencies. Only signing and on-device testing need Apple hardware.

## The loop — follow it in this order

1. **Design**: turn the request into a spec (`examples/` for the grammar,
   `assets/spec.schema.json` for the schema). Write the blueprint first: input
   surface, numbered actions with exact Apple action names, explicit variable
   wiring, indented control flow.
2. **Build**: `py scripts/build_shortcut.py spec.json -o "Name.shortcut"`.
   The build auto-validates against the lint target and refuses to emit errors.
3. **Lint**: `py scripts/validate_shortcut.py "Name.shortcut" --target ios --min-os 26`
   must report 0 errors. Treat any remaining error as a blocker.
4. **Inspect**: `py scripts/inspect_shortcut.py "Name.shortcut"` — read the
   numbered action list once to confirm it matches the intent before shipping.
5. **Sign + deliver** (Mac, or recipe without one): `references/deployment-and-debugging.md`.
6. **Test on device**: user runs it, grants first-run permissions. Watch for
   silent no-ops (a shortcut that ends on a data action shows nothing).
7. **Debug**: inspect + lint the shipped file, use the target diff, then probe
   on device. Change the **spec**, rebuild, re-lint — never hand-edit a binary plist.

## Golden rules — these are what actually break imports and runs

- **Signed vs unsigned decides everything.** iOS 15+ imports only SIGNED
  (AEA1) files; only macOS can sign. An unsigned file imports on a Mac and is
  refused by iOS. **Do not promise an importable `.shortcut` to a user without
  a Mac** — deliver a numbered build recipe or an iCloud-link path instead,
  and say so early.
- **Token strings.** A variable inside text is a `WFTextTokenString`: the
  invisible U+FFFC (`￼`) placeholder in the string plus its exact **UTF-16
  code-unit offset** in `attachmentsByRange` (length always 1; an emoji before
  the placeholder counts as 2). The spec builder computes offsets for you —
  never hand-place them.
- **UUIDs.** Every action gets a unique, real, uppercase `UUID`. References
  point at an action that has **already run**; pointing forward = silently
  empty value. Duplicates and `AAAAAAAA-…` placeholders are fatal.
- **Condition codes are integers, not names.** `0` is *less than*, not
  "equals". String equality is `4`, "contains" is `99`, "has any value" is
  `100`. Every condition needs an explicit `WFInput` and the literal field
  its code requires (`WFConditionalActionString` / `WFNumberValue`). Full
  table: `references/file-format.md`.
- **Right key, right action.** The wrong input key imports cleanly and shows
  an **empty field** — the most common silent failure. Replace Text takes
  `WFInput`; Change Case takes `text`. Never guess parameter keys: build the
  action once in Shortcuts.app, dump it with `inspect_shortcut.py`, copy the
  skeleton (the "skeleton trick").
- **Control flow.** `GroupingIdentifier` (UUID string) + integer
  `WFControlFlowMode` (0 open / 1 middle / 2 close); the closer reuses the
  opener's identifier *and* action identifier. An unclosed block corrupts
  everything after it.
- **Math.** Addition omits `WFMathOperation`; division is `÷` (U+00F7),
  multiplication is `×` (U+00D7). ASCII `/` or `*` silently renders as `+`.
- **Platform gating.** `runshellscript`, `runapplescript`,
  `runjavascriptforautomation` are **macOS only**. Storage actions
  (`getstoredcontent`…) are **OS 27+**. Use Model (`askllm`) needs Apple
  Intelligence hardware. Lint with the right `--target`/`--min-os`.
- Text action is `is.workflow.actions.gettext`, never `.text`. Never emit
  `is.workflow.actions.input` — use an `ExtensionInput` attachment. Show
  Result was renamed **Show Content** in iOS 26 (identifier unchanged:
  `showresult`). If `WFWorkflowName` is missing, the file name becomes the
  shortcut name.

## Tools (Python 3 standard library, no installs)

| Script | What it does |
|---|---|
| `scripts/build_shortcut.py` | JSON spec → unsigned `.shortcut` (binary; `--xml` for review). Auto-lints, refuses errors. `--seed` for reproducible builds. |
| `scripts/validate_shortcut.py` | Target/OS-aware lint with stable codes (`E_*`, `W_*`, `I_*`). `--target ios|macos|both`, `--min-os N`, `--json`, `--fail-on-warning`. Exit 1 on errors. |
| `scripts/inspect_shortcut.py` | Human-readable numbered action dump; `--json` for the raw plist. |
| `scripts/fix_shortcut.py` | Provably-safe machine repairs only (math operators, token offsets, icon colour). Refuses to write while design errors remain. |
| `scripts/test_lint.py` | Proves the linter catches every failure mode it claims (30 checks). Run after changing rules. |
| `scripts/make_fixture.py` | Regenerates the deliberately-broken demo fixture (deterministic — byte-identical every run). |
| `scripts/shortcut_lib.py` | Spec engine: token strings, control flow, typed convenience actions. |

## The target-diff diagnostic — use it first when debugging

When a shortcut "works on my Mac but not on my iPhone", lint it twice and diff:

```bash
py scripts/validate_shortcut.py file.shortcut --target macos --min-os 26
py scripts/validate_shortcut.py file.shortcut --target ios   --min-os 26
```

Errors present **only in the iOS run** are platform bugs by definition — a
macOS-only action, an OS-gated action, or a permission that exists on one
platform only. The diff *is* the diagnosis. Same trick with `--min-os 26`
vs `--min-os 27` for version gating.

## Debugging a failing shortcut (top-down)

1. **Reproduce** manually in the editor with the exact failing input.
   Automations/Siri add permissions and lock-state a manual run does not —
   debug the manual path first.
2. **Lint + target-diff** (above). Most "broken" files are structural.
3. **Inspect** the shipped file, not the spec.
4. **Bisect** with **Show Content** after the suspect action; **Show Alert**
   when you need a Cancel to stop a destructive run; **Quick Look** for types.
   First wrong value = failing action.
5. **Check types** (text ≠ number), **wiring** (right variable? runs before?
   inside an untaken branch?), **permissions** ("Allow Running Scripts",
   Privacy grants — denied Photos returns *empty*, not an error), and
   **environment** (locked device, Low Power Mode, Focus silencing output,
   iCloud sync lag).

Symptom → cause → fix tables: `references/deployment-and-debugging.md`.
Linter codes and known false positives: `references/lint-rules.md`.

## Output contract

Deliver, in this order:

1. **The `.shortcut` file** (unsigned is fine if a Mac will sign) — or a
   numbered build recipe if the user has no Mac.
2. **The lint result** — error count, and any warnings you did not fix.
3. **The exact sign + delivery commands**, with the macOS-only constraint
   stated if it applies.
4. **What to verify on-device** — the specific behaviour to confirm, and the
   permissions/settings to grant first.

When debugging an existing shortcut, lead with the root cause and the action
that produces it — not a description of the whole file.

## Failure handling

- **No Mac available** → never claim deployable. Plist + signer script, or a
  Shortcuts.app build recipe. Say it plainly.
- **Signed file (`AEA1` magic)** → cannot be parsed or linted. Ask for an
  unsigned export or the iCloud `downloadURL` plist (see `file-format.md`).
- **Linter errors you cannot fix** → say which and why. A file that fails
  lint but "probably works" is worse than an honest gap.
- **Third-party App Intent actions** → identifiers/schemas come from the app,
  not Apple. The linter cannot validate them (`W_FOREIGN_IDENTIFIER`); verify
  in the app and note it.
- **Automation differs from manual run** → manual path first, then trigger
  permissions, Run Immediately, lock state, corrupted trigger (delete and
  recreate the trigger, keep the shortcut).
- **User wants an OS 27 feature on OS 26** → name the exact action and
  version requirement instead of shipping something that fails silently.

## References — read when the task touches that area

- `references/file-format.md` — containers (unsigned vs AEA1), root keys,
  action schema, token strings, control flow + full condition-code table,
  input-key table, math operators, platform/OS gating, extracting plists.
- `references/lint-rules.md` — every lint code, typical fixes, target-diff
  method, known false positives.
- `references/deployment-and-debugging.md` — signing gate, delivery channels,
  URL schemes, macOS CLI, permissions, debugging playbook, symptom table,
  improvement + release checklists.

## Examples

- **Example 1 — build and ship.** *"Make a shortcut that turns the clipboard
  into a lowercase slug and copies it back."* → Blueprint (Get Clipboard →
  Change Case → Copy to Clipboard → Show Content) → spec → build → lint
  `--target ios --min-os 26` → `shortcuts sign --mode anyone` on a Mac →
  iCloud link. Tell the user: paste "Hello World", run, clipboard becomes
  "hello-world".
- **Example 2 — debug "it does nothing".** Ask for the file, lint both
  targets, look for `E_INPUT_KEY` / `E_DANGLING_REF` / `E_UNCLOSED_GROUP`,
  check the last action (`W_NO_VISIBLE_OUTPUT`), then bisect on device.
- **Example 3 — never appears in the Share Sheet.** Check
  `WFWorkflowInputContentItemClasses` is present, the Share Sheet toggle is
  on, and the shortcut accepts the shared content type.
- Working specs: `examples/open-first-url.json`, `examples/post-clipboard.json`.
  The full broken → diagnosed → fixed walkthrough: `docs/demo-walkthrough.md`.
