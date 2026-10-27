#!/usr/bin/env python3
"""Check that no secret is committed, and that the log holds no secret.

Two checks:

1. The repository carries no key. The pattern is the one the official
   disqualification checklist suggests, widened a little.
2. The traces carry no key. A trace is written by the run, so a secret
   that leaked into one would have leaked into the demo.

    python3 scripts/secret_scan.py

Exit status 0 when nothing was found, 1 otherwise.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(?<![a-z0-9])(?:api[_-]?key|secret|password|[a-z_]*token)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}"),
]

# Files that hold placeholders or the patterns themselves.
SKIP = {
    ".git", "__pycache__", ".venv", "node_modules", "logs",
}

# The local secret stores. They are gitignored on purpose, so a key in
# one of them is exactly where it belongs.
LOCAL_ENV = {".env", ".env.local"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".xlsx",
                 ".db", ".pyc", ".woff", ".woff2", ".ttf"}

# The placeholders that are allowed to appear.
ALLOWED = {
    "replace-me", "your-token", "your-token-here", "changeme", "example",
    "placeholder", "xxx", "todo", "none", "",
}


def iter_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name in LOCAL_ENV:
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            continue
        yield path


def scan_text(text):
    """The findings in one piece of text."""
    findings = []
    for pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0).strip()
            if value.lower() in ALLOWED:
                continue
            if "replace" in value.lower():
                continue
            findings.append((pattern.pattern, value[:40]))
    return findings


def main():
    problems = []

    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, value in scan_text(text):
            problems.append((str(path.relative_to(ROOT)), pattern, value))

    # The traces are written by the runs, so they are checked too.
    for path in sorted((ROOT / "logs").glob("*.jsonl")) if (ROOT / "logs").exists() else []:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, value in scan_text(text):
            problems.append((f"logs/{path.name}", pattern, value))

    if problems:
        print(f"{len(problems)} possible secret(s):")
        for where, pattern, value in problems:
            # The value is never printed: this script may end up in a
            # screenshot.
            print(f"  {where}: matches {pattern}")
        print()
        print("Rotate the key with the provider first, then remove it.")
        return 1

    print("No secrets found in the repository or in the traces.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
