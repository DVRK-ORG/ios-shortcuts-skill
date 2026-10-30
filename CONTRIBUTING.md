# Contributing

Thanks for helping make shortcut tooling less painful. This project is small on purpose: keep it simple, dependency-free, and honest.

## Ground rules

- **Python standard library only.** No new third-party dependencies in `scripts/`. If a change needs one, open an issue first.
- **Never hand-edit a binary plist.** Change the spec or the builder, rebuild, re-lint, re-inspect.
- **Every lint rule ships with a test.** Add the failing fixture case to `scripts/test_lint.py` in the same change; `py scripts/test_lint.py` must pass 25+ checks.
- **The fixer stays conservative.** It may only apply repairs that are provably behaviour-preserving. Anything needing a design decision belongs in the linter's message, not in a guess.
- **Honesty about signing.** Never document or imply a path to an iOS-importable file that skips macOS signing.

## Workflow

1. Fork and branch from `main`.
2. Make the change (spec builder, linter, references, or docs).
3. Run the full check suite:

   ```bash
   py scripts/test_lint.py
   py scripts/build_shortcut.py assets/example-hello.json -o "output/Hello You.shortcut"
   py scripts/build_shortcut.py examples/post-clipboard.json -o "output/Post Clipboard.shortcut"
   py scripts/validate_shortcut.py "output/Post Clipboard.shortcut" --target ios --min-os 26
   ```

4. If you touched the broken-fixture spec, regenerate it: `py scripts/make_fixture.py`.
5. Open a PR describing the bug or rule, the failing case it catches, and the before/after lint output.

## Reporting bugs

Include: your OS, the exact command, the lint output (add `--json` when you can), and — if a shortcut misbehaves on device — the action index where it stops (as numbered by `scripts/inspect_shortcut.py`).

## Code style

Match the surrounding code: small functions, coded findings, comments that explain *why* (usually an Apple behaviour), not *what*.
