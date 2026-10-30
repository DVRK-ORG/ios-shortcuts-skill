# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [SemVer](https://semver.org/).

## [1.0.0] — 2026-10-30

First public release — a hybrid skill combining a deep, target-aware linter, a JSON spec builder, and field debugging guidance in one dependency-free Python toolchain.

### Added

- **Spec builder** (`scripts/build_shortcut.py` + `scripts/shortcut_lib.py`): JSON spec → unsigned `.shortcut`, with token-string UTF-16 offsets computed automatically and an auto-lint gate that refuses to emit errors. Typed verbs for clipboard, link detection, first-item, case change, regex replace, calculation, and Send Message.
- **Target/OS-aware linter** (`scripts/validate_shortcut.py`): coded findings (`E_*`, `W_*`, `I_*`), `--target ios|macos|both`, `--min-os`, `--json`, `--fail-on-warning`, stable exit codes. Catches platform gating (macOS-only, OS 27, Apple Intelligence), condition-literal mismatches, wrong input keys, ASCII math operators, token-range errors, dangling/forward references, and unbalanced control flow.
- **Conservative fixer** (`scripts/fix_shortcut.py`): repairs only provable issues (math operators, token offsets, icon colour) and refuses to write while design errors remain.
- **Inspector** (`scripts/inspect_shortcut.py`): numbered, human-readable action dumps.
- **Lint test suite** (`scripts/test_lint.py`): 25 checks covering every claimed failure mode, including the iOS/macOS target diff.
- **Demo fixture + walkthrough**: a deliberately broken shortcut (`examples/broken-post-clipboard.*`) diagnosed and fixed end-to-end in `docs/demo-walkthrough.md`.
- **References**: file format with the verified condition-code table, the full lint-rule catalogue, and a deployment/debugging guide with a symptom → cause → fix table.
- **Examples**: Hello You, API Guard, Post Clipboard, Open First URL in Clipboard.

### Notes

- Corrected condition-code map (verified against real exports): `0` is less-than, `4` is string-equals, `5` is not-equals, `99` contains, `100` has-any-value. Several published guides document these incorrectly; the builder defaults to `100` and the linter requires the literal field each code needs.
- On-device import and signing require Apple hardware (macOS `shortcuts sign`) and are covered by the release checklist rather than automated tests.
