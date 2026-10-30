# Security Policy

## Reporting a vulnerability

Please report security issues privately via a GitHub security advisory (Repository → Security → Advisories) rather than a public issue. Include the affected script, a minimal spec or plist that reproduces the problem, and the impact you believe it has.

## Scope notes

- This toolchain **parses untrusted `.shortcut` files** with Python's `plistlib`. Treat shortcuts from strangers as untrusted input: lint and inspect before importing, and never import a shortcut you have not read. As Apple puts it: *"Apple cannot verify the authenticity or behavior of shortcuts shared privately."*
- **Never hardcode API keys, tokens, or passwords** in specs you share. Use `WFWorkflowImportQuestions` or a config file the shortcut reads — see `references/deployment-and-debugging.md`.
- Signing (`shortcuts sign --mode anyone`) notarizes through iCloud and sends a copy of the shortcut to Apple. Use `--mode people-who-know-me` when a shortcut contains anything sensitive.
- Generated `.shortcut` files in `output/` are local build artifacts and are git-ignored by default.
