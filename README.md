<div align="center">

<img src="docs/banner.png" alt="iOS Shortcuts Skill — build, lint, debug and ship Apple Shortcuts from any agent, on any OS" width="100%">

# iOS Shortcuts Skill

**Build, lint, debug, and ship Apple Shortcuts from any AI agent — on any OS, including Windows.**

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies: none](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#quick-start)
[![Lint tests](https://img.shields.io/badge/lint%20tests-25%2F25-blue.svg)](#testing)

*Stop hand-editing plists. Stop shipping shortcuts that silently do nothing.*

</div>

---

Most shortcut generators hand you a `.shortcut` file and wish you luck. This skill does the opposite: it **lints before it ships**, explains *why* a shortcut fails in coded, actionable findings, and is honest about the one step that truly needs a Mac — signing.

## Why this skill?

| Problem | What usually happens | What this skill does |
|---|---|---|
| Wrong parameter key | Imports fine, field shows empty on device | `E_INPUT_KEY` catches it before shipping |
| macOS-only action on iPhone | "Works on my Mac, not my phone" mystery | Target-diff: lint `--target ios` vs `--target macos`, the diff *is* the diagnosis |
| Bad token offset | Variable renders as literal `￼` or empty | Builder computes UTF-16 offsets for you; linter verifies them |
| ASCII `/` instead of `÷` | Division silently becomes addition | `E_MATH_OP` + safe auto-fix |
| No Mac available | Tools promise an importable file anyway | Honest path: build recipe or signing hand-off, stated up front |
| Unclosed If block | Everything after it corrupts | `E_UNCLOSED_GROUP` with the exact group |

## Highlights

- **Zero dependencies** — Python 3 standard library only. No `pip install`, no Node, no Xcode.
- **Runs anywhere** — Windows, macOS, Linux. Build and lint on Windows; sign on any Mac.
- **Coded lint findings** — stable `E_*` / `W_*` / `I_*` codes with `--json` output for agents and CI.
- **Target- and OS-aware** — `--target ios|macos|both`, `--min-os 26|27` gating for platform- and version-only actions.
- **Conservative fixer** — repairs only provably safe issues (math operators, token offsets, icon colour) and *refuses to write* while design errors remain.
- **Spec builder** — author shortcuts as readable JSON, never as hand-placed binary plists.

## Quick start

```bash
# 1. Build from a spec (auto-lints; refuses to emit errors)
py scripts/build_shortcut.py examples/post-clipboard.json -o "Post Clipboard.shortcut"

# 2. Lint for your real target
py scripts/validate_shortcut.py "Post Clipboard.shortcut" --target ios --min-os 26

# 3. Read it back before shipping
py scripts/inspect_shortcut.py "Post Clipboard.shortcut"

# 4. Sign on a Mac (the only Mac-only step), then AirDrop / iCloud-link it
shortcuts sign --mode anyone --input "Post Clipboard.shortcut" --output "Post Clipboard signed.shortcut"
```

> On macOS/Linux, replace `py` with `python3`.

No Mac? Read [No Mac? No problem — honestly](#no-mac-no-problem--honestly) before promising anyone a file.

## The flagship trick: target-diff debugging

When a shortcut *"works on my Mac but not on my iPhone"*:

```bash
py scripts/validate_shortcut.py broken.shortcut --target macos --min-os 26
py scripts/validate_shortcut.py broken.shortcut --target ios   --min-os 26
```

Errors that appear **only in the iOS run** are platform bugs by definition. You don't read 30 actions by hand — the diff points at the culprit. Same trick with `--min-os 26` vs `--min-os 27` for version gating.

Full worked example: [docs/demo-walkthrough.md](docs/demo-walkthrough.md) — a deliberately broken shortcut, diagnosed and fixed step by step.

## Tools

| Script | Purpose |
|---|---|
| `scripts/build_shortcut.py` | JSON spec → unsigned `.shortcut` (binary or `--xml`). Auto-lints, refuses errors. |
| `scripts/validate_shortcut.py` | Target/OS-aware linter. Coded findings, `--json`, `--fail-on-warning`, stable exit codes. |
| `scripts/inspect_shortcut.py` | Human-readable numbered action dump; `--json` for the raw plist. |
| `scripts/fix_shortcut.py` | Provably-safe repairs only. Refuses to write while design errors remain. |
| `scripts/test_lint.py` | 25 checks proving the linter catches every failure mode it claims. |
| `scripts/make_fixture.py` | Regenerates the deliberately broken demo fixture. |
| `scripts/shortcut_lib.py` | Spec engine: token strings, control flow, typed convenience actions. |

## Write a spec, not a plist

```json
{
  "name": "Post Clipboard",
  "actions": [
    { "do": "getclipboard", "as": "clip" },
    { "do": "changecase", "input": "{clip}", "case": "lowercase", "as": "lower" },
    { "do": "if", "group": "g1", "input": "{lower}", "condition": 100 },
    { "do": "show", "text": "Clipboard: {lower}" },
    { "do": "endif", "group": "g1" }
  ]
}
```

`{name}` placeholders become real `WFTextTokenString` attachments with correct UTF-16 offsets — including the emoji-counts-as-2 trap — computed by the builder. Schema: [`assets/spec.schema.json`](assets/spec.schema.json). Working specs: [`examples/`](examples/).

## No Mac? No problem — honestly

iOS 15+ imports **only signed** `.shortcut` files, and only macOS can sign (`shortcuts sign`). There is no Windows or iOS workaround, and this skill will not pretend otherwise.

Without a Mac you still get real value:

1. **Build + lint + inspect** the full shortcut on Windows/Linux and know it is structurally sound.
2. **Deliver a numbered build recipe** the user assembles in Shortcuts.app in minutes, *or*
3. **Hand off the unsigned file + one signing command** for any Mac the user can borrow, *or*
4. Ship via an **iCloud link** once the shortcut exists on any Apple device.

That honesty is a feature. A signed-file promise that fails at import time is not.

## Examples

| Spec | What it does |
|---|---|
| [`assets/example-hello.json`](assets/example-hello.json) | Ask for a name → notification → on-screen greeting |
| [`assets/example-api-guard.json`](assets/example-api-guard.json) | Fetch an API, branch on its `status` key, alert or show the message |
| [`examples/post-clipboard.json`](examples/post-clipboard.json) | Lowercase the clipboard, strip a `posted:` marker, send it — with an empty-clipboard guard |
| [`examples/open-first-url.json`](examples/open-first-url.json) | Open the first URL found in the clipboard |
| [`examples/broken-post-clipboard.json`](examples/broken-post-clipboard.json) | Deliberately broken twin of Post Clipboard — the debugging demo fixture |

## Repository layout

```
.
├── SKILL.md                  # the agent skill itself (start here if you are an agent)
├── README.md
├── assets/                   # spec schema + starter specs
├── examples/                 # working specs + the broken demo fixture
├── scripts/                  # builder, linter, inspector, fixer, tests (stdlib only)
├── references/               # file format, lint rules, deployment & debugging
├── docs/                     # banner + broken → diagnosed → fixed walkthrough
└── evals/                    # evaluation prompts for agent behaviour
```

**Using this as an agent skill?** Drop the folder where your agent loads skills from and point it at `SKILL.md`. It follows the [Agent Skills](https://agentskills.io) `SKILL.md` format.

## Testing

```bash
py scripts/test_lint.py
# 25/25 passed

# Rebuild every shipped example and lint it clean
py scripts/build_shortcut.py assets/example-hello.json -o "output/Hello You.shortcut"
py scripts/build_shortcut.py examples/post-clipboard.json -o "output/Post Clipboard.shortcut"
py scripts/validate_shortcut.py "output/Post Clipboard.shortcut" --target ios --min-os 26
```

On-device import and signing still need real Apple hardware — see the release checklist in [`references/deployment-and-debugging.md`](references/deployment-and-debugging.md).

## References

- [`references/file-format.md`](references/file-format.md) — containers, token strings, control flow, the full condition-code table, input keys, platform gating
- [`references/lint-rules.md`](references/lint-rules.md) — every lint code, typical fixes, known false positives
- [`references/deployment-and-debugging.md`](references/deployment-and-debugging.md) — signing gate, delivery channels, permissions, symptom → cause → fix table

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). If you add a lint rule, add its test in `scripts/test_lint.py` in the same change.

## License

[MIT](LICENSE)

## Project files

- [CHANGELOG.md](CHANGELOG.md) — release history
- [SECURITY.md](SECURITY.md) — reporting a vulnerability, and how to handle untrusted shortcuts
- [evals/evals.json](evals/evals.json) — evaluation prompts for agent behaviour
