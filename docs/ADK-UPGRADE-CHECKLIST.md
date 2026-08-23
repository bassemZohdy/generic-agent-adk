# ADK Upgrade Checklist

Use this checklist whenever the `google-adk` dependency is upgraded. The
automated guard is intentionally narrow: it catches removed imports and
signature changes, while the matrix below protects behavior that depends on
ADK event and state semantics.

## Automated checks

```sh
uv run python scripts/check-adk-assumptions.py
uv run pytest tests/test_workflow_invocations.py -q
```

Confirm that the supported version range in `pyproject.toml`, the lockfile,
ADR-003, and this checklist agree.

## Manual compatibility matrix

- Re-verify the workflow/graph surface (ADR-005, Phase B): `google.adk.workflow`
  exports, `BaseNode` pydantic fields, `Runner(node=...)` root construction,
  the `google.adk.workflow._llm_agent_wrapper` task-mode wrapper, and
  `FINISH_TASK_TOOL_NAME` in `google.adk.agents.llm.task._finish_task_tool`.
  These surfaces are **younger than the legacy
  `SequentialAgent`/`ParallelAgent`/`LoopAgent` classes** and must be
  re-verified on every upgrade; `scripts/check-adk-assumptions.py` asserts
  their existence and signatures, and `tests/test_workflow_gates.py` proves
  they run (Phase B).
- Verify `google.adk.tools.agent_tool._TaskAgentTool` on every upgrade: the
  approval policy's `is_unconditional_tool` imports this private symbol for
  delegation detection. If it moves or is renamed, detection fails CLOSED
  with logged warnings — approval gating becomes stricter (more tools
  gated), never silently permissive.
- Run all eight YAML examples through a real ADK `Runner` and confirm the
  expected final agent/output event.
- Exercise approval confirmation with approve, reject, disconnect, and resume
  paths; verify that the mutating tool never runs before approval.
- Exercise REST and Live transports with anonymous and authenticated sessions,
  including reconnect/resume and session-state isolation.
- Re-check before/after agent and tool callbacks, parallel branch aggregation,
  loop bounds, and state/output keys.
- Re-run the Docker code-execution hardening checks with the pinned sandbox
  digest and verify that unpinned production overrides fail closed.
- Review ADK deprecation warnings and update ADR-003's migration gate.

Record the ADK version, test command, and evidence in the upgrade PR before
removing the upper version bound.
