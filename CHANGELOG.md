# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [1.0.1] — 2026-10-30

Five defects found in a review of `v1.0.0`. All are fixed, each with a regression test.

### Fixed

- **The fixer could swap variables and report success.** `fix_shortcut.py` re-bound token attachments to placeholders *positionally*. Because a plist may list its `attachmentsByRange` keys in any order, this swapped two variables: the file imported cleanly, linted clean, and every value landed in the wrong field. The fixer now keeps every attachment bound to the placeholder it already sits on, and only moves an attachment whose offset is not a placeholder at all — and only when exactly one placeholder is left unclaimed, so the mapping is forced and provable. Ambiguous cases are left untouched and stay flagged.
- **Invalid block nesting passed validation.** Control flow was checked by counting openers and closers per group, which cannot see crossing blocks. The linter now walks a stack of open blocks: `E_GROUP_NESTING` for crossing blocks, `E_ORPHAN_BRANCH` for an Otherwise/menu case with no open block.
- **`{input}` failed inside text fields.** The builder only resolved `{input}` in whole-value inputs; a text field raised `unknown placeholder`. `{input}` now resolves to the Shortcut Input in text fields too.
- **Download request bodies kept placeholders as literal text.** `download(..., extra=...)` merged extra parameters verbatim. Extra parameters are now resolved recursively, and the `{"Value": "text"}` shape is promoted to a real `WFTextTokenString`, so a request body carries an attachment instead of literal braces.
- **Custom icons used incorrect output keys.** A spec written as `{"icon": {"glyph": …, "color": …}}` emitted those keys verbatim into the plist; the shortcut imported with a generic icon and only a warning to explain it. The builder now normalises friendly *and* raw keys to `WFWorkflowIconGlyphNumber` / `WFWorkflowIconStartColor`, and `E_ICON_KEYS` reports unknown icon keys as an error.

### Added

- `E_TOKEN_REF` — an attachment that names a different output than the action it points at produces.
- `E_ICON_KEYS` — `WFWorkflowIcon` containing keys that are not real plist keys.
- `E_GROUP_NESTING`, `E_ORPHAN_BRANCH` — control-flow structure checks.
- `W_LITERAL_PLACEHOLDER` — a `{name}` left as literal text in a field that interpolates.
- The lint test suite grew from 30 to **49 checks**, including a regression for each defect above.

## [1.0.0] — 2026-10-30

First public release — a hybrid skill combining a deep, target-aware linter, a JSON spec builder, and field debugging guidance in one dependency-free Python toolchain.

### Added

- **Spec builder** (`scripts/build_shortcut.py` + `scripts/shortcut_lib.py`): JSON spec → unsigned `.shortcut`, with token-string UTF-16 offsets computed automatically and an auto-lint gate that refuses to emit errors. Typed verbs for clipboard, link detection, first-item, case change, regex replace, calculation, and Send Message. `--seed` makes a build byte-reproducible.
- **Target/OS-aware linter** (`scripts/validate_shortcut.py`): coded findings (`E_*`, `W_*`, `I_*`), `--target ios|macos|both`, `--min-os`, `--json`, `--fail-on-warning`, stable exit codes. Catches platform gating (macOS-only, OS 27, Apple Intelligence), condition-literal mismatches, wrong input keys, ASCII math operators, token-range errors, dangling/forward references, and unbalanced control flow.
- **Conservative fixer** (`scripts/fix_shortcut.py`): repairs only provable issues (math operators, token offsets, icon colour) and refuses to write while design errors remain.
- **Inspector** (`scripts/inspect_shortcut.py`): numbered, human-readable action dumps.
- **Lint test suite** (`scripts/test_lint.py`): 30 checks covering every claimed failure mode, including the iOS/macOS target diff and reproducible-build guarantees.
- **Demo fixture + walkthrough**: a deliberately broken shortcut (`examples/broken-post-clipboard.*`) diagnosed and fixed end-to-end in `docs/demo-walkthrough.md`.
- **References**: file format with the verified condition-code table, the full lint-rule catalogue, and a deployment/debugging guide with a symptom → cause → fix table.
- **Examples**: Hello You, API Guard, Post Clipboard, Open First URL in Clipboard.

### Notes

- Corrected condition-code map (verified against real exports): `0` is less-than, `4` is string-equals, `5` is not-equals, `99` contains, `100` has-any-value. Several published guides document these incorrectly; the builder defaults to `100` and the linter requires the literal field each code needs.
- The demo fixture is generated with a fixed UUID seed, so `py scripts/make_fixture.py` reproduces the committed file byte-for-byte and never dirties the working tree.
- `.gitattributes` pins LF line endings for text files and marks binary assets (including the fixture plist) as non-text, so clones are identical across Windows, macOS, and Linux.
- On-device import and signing require Apple hardware (macOS `shortcuts sign`) and are covered by the release checklist rather than automated tests.
