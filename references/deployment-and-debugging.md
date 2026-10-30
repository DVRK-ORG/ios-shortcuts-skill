# Deploying, running, and debugging Shortcuts

## The signing gate — read this first

| Step | Where | Notes |
|---|---|---|
| Build a `.shortcut` | Anywhere (Windows/Linux/Mac) | A plist. Parseable and lintable. |
| **Sign it** | **macOS only** | `shortcuts sign`. No iOS or Windows equivalent exists. |
| Import on iPhone/iPad | iOS 15+ | **Only signed files import.** |
| Import on Mac | macOS 12+ | Unsigned files import fine on a Mac. |
| Import unsigned file | iOS 13/14 only | Needs Settings → Shortcuts → **Allow Untrusted Shortcuts** (the toggle is grayed out until any shortcut has run once). |

Consequences worth stating plainly to a user:

1. If the user has no Mac, you cannot ship them an importable `.shortcut`
   file. Ship a **build recipe** (numbered actions) for the Shortcuts app, or a
   plist plus a one-command signing script they run on any Mac they can borrow.
2. Signing `anyone` mode **notarizes through iCloud**: it requires a signed-in
   iCloud session and network access, and sends a copy of the shortcut to
   Apple for validation. `people-who-know-me` signs locally and restricts
   import to the user's own devices and contacts.
3. If `shortcuts sign` rejects a generated plist ("isn't in the correct
   format"): convert first (`plutil -convert binary1 in -o out`), run the
   linter and fix everything it flags, or build a one-action skeleton in
   Shortcuts.app, export it, and modify that plist.

```bash
# on the Mac
shortcuts sign --mode anyone --input "In.shortcut" --output "Out signed.shortcut"
shortcuts sign --mode people-who-know-me --input "In.shortcut" --output "Out signed.shortcut"
```

## Delivery channels

Ranked by what the user is most likely to want.

### 1. iCloud link (best for sharing with other people)

In Shortcuts.app: shortcut → Share → **Copy iCloud Link**. Produces
`https://www.icloud.com/shortcuts/<uuid>`. The recipient taps it and gets an
"Add Shortcut" prompt. Signing happens server-side. Caveat: the link is
effectively public once sent.

### 2. Signed file (AirDrop / Files / Mail / Messages)

Signed `.shortcut` → AirDrop to iPhone → tap → **Add Shortcut**. Also works
from iCloud Drive via the Files app. Email/Messages attachments often land in
a "you can't preview this" state — recipients must still tap through.

### 3. iCloud sync (simplest, for the user's own devices)

Create/edit on one device with iCloud sync on; it appears on the others.
**Sync is eventual, not synchronous** — allow seconds to minutes. If it does
not appear, toggle Shortcuts in Settings → iCloud → Show All → Shortcuts.

### 4. Import from URL

`shortcuts://import-shortcut/?url=<encoded>&name=<name>` (optional
`&silent=true`) — host the file somewhere reachable; on iOS 15+ the served
file must be signed. RoutineHub's HubSign service can sign files without a
Mac for public distribution.

### URL schemes (for triggering, not installing)

```
shortcuts://run-shortcut?name=NAME&input=text&text=URLENCODED
shortcuts://run-shortcut?name=NAME&input=clipboard
shortcuts://open-shortcut?name=NAME
shortcuts://create-shortcut
shortcuts://gallery
shortcuts://automations
```

Use the **Run Shortcut action** to run a shortcut from inside another shortcut —
the URL scheme crosses an app boundary and loses context. `run-shortcut`
supports x-callback-url (`x-success`, `x-cancel`, `x-error`). The legacy
`workflow://` scheme still works as an alias.

## Running from the command line (macOS only)

`/usr/bin/shortcuts` exists on macOS 12 (Monterey) and later. There is **no
CLI on iOS**.

```bash
shortcuts list                          # all shortcut names
shortcuts list --folders                # folders instead
shortcuts list --show-identifiers       # names + UUIDs (prefer UUIDs — names collide)

shortcuts run "Name"                    # run by name
shortcuts run "Name" -i in.jpg -o out   # input file -> output file (- repeatable, - = stdin/stdout)
shortcuts run "Name" --output-type public.plain-text

shortcuts view "Name"                   # open in the editor (launches the GUI)
shortcuts sign --mode anyone -i in.shortcut -o out.shortcut
```

Notes: `run`, `view`, and `sign` launch the Shortcuts.app GUI; only `list`
works headless. There is no `shortcuts import` — import is GUI-only
(`open -a Shortcuts file.shortcut`). Exit code is `0` on success, `1` on error.

On Mac, shortcuts also live in `~/Library/Shortcuts/Shortcuts.sqlite` — the
`ZDATA` column is a binary plist holding the action list.

## Permissions the user must grant

### "Allow Running Scripts" (required for script actions)

**Settings → Apps → Shortcuts → Advanced → Allow Running Scripts** on iOS 17+;
**Settings → Shortcuts → Advanced** on iOS 16 and earlier. Required for: Run
JavaScript on Web Page, Run Script over SSH, and (on Mac) Run Shell Script /
Run AppleScript. Without it the shortcut fails with a security-settings error.

### Per-app data permissions

**Settings → Privacy & Security → Photos → Shortcuts**. If Photos access is
off, **Find Photos returns an empty list** — it does not error. Same shape of
failure for Contacts, Health, and Calendar. Check this before concluding "the
action is broken". Grant each permission on a first manual run.

### Automation permissions

- iOS 26 and earlier: Personal Automations live in the Automation tab;
  iOS 27+: automations are built into shortcuts and sync between devices.
- A shortcut triggered by an automation inherits that automation's permission
  scope. "Run Immediately" (formerly disabling *Ask Before Running*) can be
  reset by iOS updates or iCloud sync conflicts — re-check it first when an
  automation goes quiet.
- "Always Allow" on an automation permission prompt has been observed not to
  persist, re-prompting on every run — a known Apple behaviour, worth flagging
  rather than chasing.
- Locked device, Low Power Mode, and an active Focus can silently suppress or
  defer triggers/output — the shortcut may have *succeeded* while its
  notification was silenced.

### Share Sheet visibility

A shortcut must be enabled in **Settings → Apps → Shortcuts → Share Sheet**
and have at least one entry in `WFWorkflowInputContentItemClasses`, otherwise
it never appears when sharing. It also only appears for content types it
accepts.

## Debugging playbook

iOS has **no console** for Shortcuts. Debugging = offline linting + on-device
probes. Work top-down; each step narrows the search.

### 1. Reproduce with a minimal input

Run the shortcut from the Shortcuts.app editor with the exact input that
fails. Automations and Siri add variables and permissions a manual run does
not — a shortcut that works manually can still fail as an automation. Debug
the manual path first, then the trigger separately.

### 2. Lint it — and diff the targets

```bash
py scripts/validate_shortcut.py <file.shortcut> --target ios --min-os 26
```

When a shortcut "works on my Mac but not on my iPhone", **lint it twice and
diff the results**:

```bash
py scripts/validate_shortcut.py <file.shortcut> --target macos --min-os 26
py scripts/validate_shortcut.py <file.shortcut> --target ios   --min-os 26
```

Errors present only in the iOS run are platform bugs by definition. That diff
*is* the diagnosis. Rule details and known false positives:
`references/lint-rules.md`.

### 3. Bisect with an inspection action

Insert **Show Content** (formerly Show Result) after the suspect action.
**Show Alert** is better for a step-by-step trace because its Cancel button
can halt a destructive run. **Quick Look** (`is.workflow.actions.quicklook`)
is the probe that never lies about types. Trace from the first action forward;
the first probe that shows the wrong value identifies the failing action.
Label probes with `DEBUG:` comments so they are easy to strip later.

Gotchas: if Show Content shows *only the literal text* and not the variable,
the variable was never produced — the bug is upstream. On some builds Show
Content crashes on large payloads ("runner quit unexpectedly") — use Quick
Look or Show Alert instead. **View Content Graph** shows a value's type,
the fastest way to diagnose text-vs-number mismatches.

### 4–7. Check types, wiring, permissions, environment

- **Types** — text is not a number. Use Coerce Text to Number where needed.
- **Wiring** — is the input attached to the right variable? Does the
  referenced action actually run *before* this one, on this branch? An action
  inside an untaken If branch produces no output.
- **Permissions** — Allow Running Scripts; Privacy grants; automation scope.
- **Environment** — locked device, background limits, Low Power Mode, network
  availability, iCloud sync lag.

### 8. Read the logs

On the Mac, Console.app shows Shortcuts logs — filter by the `shortcuts` /
`com.apple.shortcuts` subsystem. The **Logger for Shortcuts** app (Alex Hay)
gives a real-time console via its Log Message actions.

## Symptom → cause table

| Symptom | Likely cause | Fix |
|---|---|---|
| "Couldn't add shortcut" | Unsigned file on iOS 15+ | Sign on a Mac, or share via iCloud link |
| Security-settings block (iOS 13/14) | Untrusted-shortcut block | Settings → Shortcuts → Allow Untrusted Shortcuts (run any shortcut once if grayed out) |
| Import does nothing | Missing `WFWorkflowInputContentItemClasses` | Add input content classes |
| Imported shortcut name is wrong | `WFWorkflowName` missing | Set it — otherwise the file name is used |
| Shortcut missing from Share Sheet | Share Sheet toggle off, or no input classes | Enable in Settings; add input classes |
| Shortcut empty / field blank in editor | Wrong input parameter key | Use the correct key (see `file-format.md`) |
| Variable is empty downstream | Dangling/forward reference, name mismatch, untaken branch | Linter: `E_DANGLING_REF`, `W_FORWARD_REF`; compare names exactly (case-sensitive) |
| If/loop misbehaves | `WFControlFlowMode` as string, unbalanced group, wrong end identifier | Linter catches all three; modes are ints 0/1/2 |
| Text shows raw `￼` or `{name}` | Malformed token string (offset/length/placeholder) | Build with the spec builder; linter checks offsets |
| "runner quit unexpectedly" | Show Result/Show Content crash on large or odd payloads | Replace with Quick Look or Show Alert |
| Action produces nothing | Privacy permission denied (Photos, Contacts…) | Grant in Settings → Privacy & Security |
| Script action refuses to run | "Allow Running Scripts" off | Enable in Settings → Apps → Shortcuts → Advanced |
| Automation never fires | Trigger disabled/reset, corrupted trigger record after migration/update | Re-check Run Immediately; delete and recreate the trigger (keep the shortcut) |
| Automation fires but asks every time | "Always Allow" not persisting (known Apple behaviour) | Accept the prompt; set the automation to run immediately |
| Shortcut missing on second device | iCloud sync delay | Wait; toggle Shortcuts in iCloud settings; or share the file directly |
| `shortcuts sign` fails | Not signed into iCloud (notarization) | Sign into iCloud, retry |
| `shortcuts sign` rejects the file | Input is an XML plist, or malformed generated plist | `plutil -convert binary1` first; lint and fix |
| Division computes wrong / adds instead | ASCII `/` instead of `÷` | Use U+00F7 (`scripts/fix_shortcut.py` repairs it) |
| Text becomes a number (or vice versa) | Type coercion | Coerce explicitly; check with View Content Graph |
| Nothing happens on run | Ends on a data action (`W_NO_VISIBLE_OUTPUT`) | Add Show Content / Show Alert / Show Notification at the end |
| `shortcuts run` cannot find it | Name changed, or not in the library | Use `shortcuts list --show-identifiers` and the UUID |
| Shortcut is slow | Network calls inside loops, huge lists, Get Web Page Contents on APIs | Cache responses in a variable; `downloadurl` + `detectdictionary`; extract sub-shortcuts |

## Workflow when a device test fails

1. Note the exact action index where it stops (counted from 0, as
   `scripts/inspect_shortcut.py` numbers them).
2. Inspect the file you actually shipped — not the spec — to confirm the plist
   on disk matches your intent.
3. Lint both targets; check the symptom table above for that action.
4. Insert Quick Look / Show Content probes around it, rebuild, redeploy, rerun.
5. Fix the root cause in the spec, rebuild, re-validate. Never hot-patch the
   binary plist by hand — regenerate.

## Improving an existing shortcut

- **Name the actions.** Set `CustomOutputName` on every action whose output is
  referenced. Unnamed outputs show as "Text" or "URL" in the variable picker,
  which makes a 30-action shortcut unreadable.
- **Add comments.** Plain-language `comment` actions are free and survive edits.
- **Blueprint before building.** Metadata (input surfaces + fallback), numbered
  actions with exact Apple names, explicit variable wiring and type coercions,
  indented control flow. A good blueprint is what the user assembles by hand
  when no Mac is available.
- **Extract repeated blocks into their own shortcut** past ~25–50 actions and
  call them with **Run Shortcut**, passing a single Dictionary payload.
- **Set variables once, at the top.** Gather inputs into named variables and
  reference those, instead of threading a value through many actions. Inside
  `Repeat with Each`, persist loop results with Set/Add to Variable —
  Repeat Results alone returns every iteration's last output.
- **Guard optional data.** A dictionary key that may not exist gets an If
  (`WFCondition` 100/101) before use, not an assumption. Check API responses
  for values before writing files/notes, so a network timeout never overwrites
  good data with blank.
- **Isolate credentials.** Never hardcode API keys or tokens in shared
  shortcuts — put them in a top config block bound to `WFWorkflowImportQuestions`,
  or a config file the shortcut reads.
- **Prefer built-in actions over scripts.** Faster, no "Allow Running Scripts"
  dependency, works on iOS. Lists are **1-indexed** everywhere in Shortcuts.
- **Make it idempotent.** If it can run twice (automation retrigger), make the
  second run a no-op rather than a duplicate.
- **Add an output action.** A shortcut that ends in a data action shows
  nothing. End with **Show Content** or **Show Notification**.

## Making it shareable (release checklist)

1. Build: `py scripts/build_shortcut.py spec.json -o "Name.shortcut"` (auto-validates).
2. Lint: `py scripts/validate_shortcut.py "Name.shortcut" --target ios --min-os 26` — 0 errors.
3. Inspect: `py scripts/inspect_shortcut.py "Name.shortcut"` — eyeball the action list once.
4. Set an icon (`WFWorkflowIconGlyphNumber` + `WFWorkflowIconStartColor`), a
   clear name, input classes, and `WFWorkflowImportQuestions` for anything the
   recipient must supply.
5. Sign on a Mac (or import on the owner's device and Copy iCloud Link).
6. Run once on device, grant permissions, watch for silent no-ops.
7. Document the required OS version and device (Apple Intelligence actions
   need iPhone 15 Pro or later).

Apple's own caveat, worth passing on: *"Apple cannot verify the authenticity
or behavior of shortcuts shared privately."*
