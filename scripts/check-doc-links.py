"""Fail when a relative Markdown link points to a missing repository file."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)")
errors: list[str] = []

for document in ROOT.rglob("*.md"):
    if any(part in {".git", ".venv", "htmlcov"} for part in document.parts):
        continue
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = (document.parent / target.split("#", 1)[0]).resolve()
        if not path.exists() or ROOT not in path.parents and path != ROOT:
            errors.append(f"{document.relative_to(ROOT)} -> {target}")

if errors:
    print("Broken relative Markdown links:")
    print("\n".join(errors))
    sys.exit(1)
print("Markdown relative-link check passed")
