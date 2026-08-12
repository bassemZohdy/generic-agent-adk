"""Project entry point for running the generic ADK evaluation set."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
from typing import Sequence


ROOT = Path(__file__).resolve().parent.parent
EVAL_SET = ROOT / "tests" / "eval" / "generic_agent.evalset.json"
EVAL_CONFIG = ROOT / "tests" / "eval" / "eval_config.json"


def build_eval_command(detailed: bool = False) -> list[str]:
    """Build the ADK CLI command without importing private ADK internals."""
    adk = shutil.which("adk") or "adk"
    command = [
        adk,
        "eval",
        str(ROOT / "basic_agent"),
        str(EVAL_SET),
        f"--config_file_path={EVAL_CONFIG}",
    ]
    if detailed:
        command.append("--print_detailed_results")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detailed", action="store_true", help="Print detailed ADK eval results."
    )
    args = parser.parse_args(argv)
    return subprocess.run(build_eval_command(args.detailed), cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
