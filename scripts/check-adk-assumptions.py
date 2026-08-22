"""Verify the ADK contracts recorded by ADR-003 and ADR-004.

This is a fast upgrade guard, not a replacement for the full compatibility
matrix. It fails when the locked ADK leaves the supported range or removes a
contract that the runtime relies on.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import inspect
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
MIN_ADK = (2, 6, 3)
MAX_ADK = (2, 7, 0)


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise RuntimeError(f"Unparseable google-adk version: {value}")
    return tuple(int(part) for part in match.groups())


def _require_import(module_name: str, attribute: str) -> None:
    module = importlib.import_module(module_name)
    if not hasattr(module, attribute):
        raise RuntimeError(f"{module_name}.{attribute} is missing")


def main() -> None:
    version = importlib.metadata.version("google-adk")
    parsed = _version_tuple(version)
    if not MIN_ADK <= parsed < MAX_ADK:
        raise RuntimeError(
            f"google-adk {version} is outside the supported range "
            ">=2.6.3,<2.7.0; review ADR-003 and ADR-004 before upgrading"
        )

    for module_name, attribute in (
        ("google.adk.agents", "BaseAgent"),
        ("google.adk.plugins", "BasePlugin"),
        ("google.adk.workflow", "Workflow"),
        ("google.adk.code_executors.base_code_executor", "BaseCodeExecutor"),
        ("google.adk.tools.tool_context", "ToolContext"),
    ):
        _require_import(module_name, attribute)

    from google.adk.runners import Runner
    from google.adk.tools.tool_context import ToolContext
    from google.adk.workflow import BaseNode

    runner_params = inspect.signature(Runner.run_async).parameters
    for required in ("invocation_id", "new_message", "state_delta"):
        if required not in runner_params:
            raise RuntimeError(f"Runner.run_async lost required parameter: {required}")
    confirmation_params = inspect.signature(ToolContext.request_confirmation).parameters
    for required in ("hint", "payload"):
        if required not in confirmation_params:
            raise RuntimeError(
                f"ToolContext.request_confirmation lost required parameter: {required}"
            )

    # B0 — workflow/graph surface (ADR-005, Phase B). These symbols are younger
    # than the legacy SequentialAgent/ParallelAgent/LoopAgent classes and must
    # be re-verified on every google-adk upgrade (ADK-UPGRADE-CHECKLIST.md).
    for attribute in (
        "Workflow",
        "Edge",
        "JoinNode",
        "FunctionNode",
        "Node",
        "node",
        "RetryConfig",
        "START",
        "DEFAULT_ROUTE",
    ):
        _require_import("google.adk.workflow", attribute)

    if "node" not in inspect.signature(Runner.__init__).parameters:
        raise RuntimeError("Runner lost the `node` BaseNode-root parameter")
    for field in (
        "retry_config",
        "timeout",
        "input_schema",
        "output_schema",
        "state_schema",
        "rerun_on_resume",
    ):
        if field not in BaseNode.model_fields:
            raise RuntimeError(f"BaseNode lost required field: {field}")

    importlib.import_module("google.adk.workflow._llm_agent_wrapper")
    finish_tool_name = getattr(
        importlib.import_module("google.adk.agents.llm.task._finish_task_tool"),
        "FINISH_TASK_TOOL_NAME",
        "",
    )
    if not isinstance(finish_tool_name, str) or not finish_tool_name:
        raise RuntimeError("FINISH_TASK_TOOL_NAME is missing from _finish_task_tool")

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    if not re.search(r"POST\s*:\s*[\"']?1|POST=1", compose) or not re.search(
        r"IMAGES\s*:\s*[\"']?1|IMAGES=1", compose
    ):
        raise RuntimeError("ADR-004 socket-proxy POST/IMAGES ACL contract is missing")

    print(f"ADK assumption checks passed for google-adk {version}")


if __name__ == "__main__":
    main()
