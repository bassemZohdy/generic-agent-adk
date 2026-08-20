"""Fail if a GitHub Actions workflow references a mutable action ref."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW_DIR = Path(__file__).parents[1] / ".github" / "workflows"
USES_PATTERN = re.compile(r"^\s*uses:\s*([^\s#]+)(?:\s+#.*)?$", re.MULTILINE)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def main() -> None:
    violations: list[str] = []
    for workflow in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        for line_number, line in enumerate(
            workflow.read_text(encoding="utf-8").splitlines(), start=1
        ):
            match = USES_PATTERN.match(line)
            if not match:
                continue
            reference = match.group(1)
            if "@" not in reference:
                violations.append(f"{workflow}:{line_number}: missing @SHA")
                continue
            action, ref = reference.rsplit("@", 1)
            if not action or not SHA_PATTERN.fullmatch(ref):
                violations.append(
                    f"{workflow}:{line_number}: {reference} is not pinned to a 40-character SHA"
                )
    if violations:
        raise SystemExit("\n".join(violations))
    workflow_count = len(list(WORKFLOW_DIR.glob("*.y*ml")))
    print(f"All GitHub Actions references are SHA-pinned ({workflow_count} workflows)")


if __name__ == "__main__":
    main()
