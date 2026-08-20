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
