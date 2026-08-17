# TODO — Pluggable code-execution sandbox: patch series

Design: [ADR-004](docs/ADR-004-pluggable-code-execution.md).
This series is **complete** — the table below is the landed-work record;
each patch's original spec text lives in git history alongside its commit.

**Status:** **P1–P11 all ✅ complete — series finished.** Branch `main`:

| Patch | Commit | Summary |
|---|---|---|
| P1 resolver scaffold | `dcf35b4` | `_CodeExecutionProviderSpec`, `CodeExecutionResolution`, registry, `resolve_code_executor()`; 11 tests |
| P2 docker + hardened executor | `a321312` | `HardenedContainerCodeExecutor` (cached lazy factory; mem/cpu/pids/read-only/tmpfs + wall-clock timeout w/ container recovery), docker provider (1s ping probe), `docker` extra; 13 tests; live-verified on Docker 29.6.2 |
| P3 gemini_built_in | `774f519` | isinstance(str) + `is_gemini_eap_or_2_or_above` probe; 8 tests |
| P4 unsafe_local | `16b1d4f` | explicit-override-only, `warn_on_select`; 3 tests |
| P5 settings plumbing | `0aaf737` | 7 `code_execution_*` settings fields, `ExecutionCodeExecutionConfig` (YAML `execution.code_execution.*`), `.env.example`; 4 tests |
| P6 agent wiring + tell-the-model | `98c2644` | `_build_runtime_context` resolves via `resolve_code_executor` (env + YAML overlay); RuntimeContext strategy/detail fields; instruction line per scenario; `inspect_runtime()` + `adk.capabilities` span entries; 9 tests |
| P7 GCP providers | `a25600c` | vertex_ai / agent_engine_sandbox / gke identifier-presence probes (never `GCP_PROJECT` alone — regression-tested), consolidated registration = chain order, `gke` extra + lock; 10 tests |
| P8 compose sandbox proxy | `4e4747e` | `code-exec-socket-proxy` behind `code-exec` profile (POST=1 master switch + CONTAINERS/EXEC/IMAGES/PING/VERSION), dedicated `code-exec` network, adk-api passthroughs; `docker compose config` gates verified |
| P9 test consolidation | `2328a1e`+ | full checklist verified against named tests; coverage 95.90% both with `--extra docker` (303 passed, 1 skip) and without (304 passed); remaining uncovered lines in `code_execution.py` are defensive branches only |
| P10 docs | `41029ed` | README "Code execution" section (strategy table, tradeoffs, image note), CHANGELOG series entry, ADR-004 §4 verified-proxy note + Verification check-off + corrections |
| P11 security review | `2d80e2f` | Live: proxy ACL 403s on build/auth/commit/networks/secrets/swarm with 200/201 positive controls; proxy unresolvable off the `code-exec` network; timeout-recovery verified (5.5s for a 5s timeout after fixing stop()→kill(), 15.6s before); README production-checklist paragraph; all 8 ADR-004 Verification items ✅ |

Baseline commit `5e747d0`: Skills support + ADR-004 + the previous
13-task TODO (see git history, which also preserves the full original
text of patches P1–P11). Old-task → patch mapping: 1→P1, 2+3→P2, 4→P3,
6→P4, 7→P5, 8+9→P6, 5→P7, 10→P8, 11→P9, 12→P10, 13→P11.

All gates were run per patch; CI enforces them continuously. The verified-
facts appendices that used to live here moved into
[ADR-004](docs/ADR-004-pluggable-code-execution.md) (Appendices A/B).

---

Completed work is recorded in [CHANGELOG.md](CHANGELOG.md). Design
decisions are recorded as ADRs in [docs/](docs/).

---

## Cleanup completed — 2026-08-17

- [x] Removed the stale `TODO P11 security review` marker from the
  `code-exec` network definition in `docker-compose.yml`; P11 is complete.

## Open items — 2026-08-17

Verified against the current tree after the docs/CMD/CVE fix series. The
2026-08-15 security-and-correctness hardening landed in full (identity
binding, fail-closed auth, realm dev/prod split, locked non-root builds,
constant-time service keys, JWKS caching, WS hardening, prompt-injection
framing, rate limits, tool audit callbacks, `execution.steps`/`workers`
wiring, custom-module allowlisting) — none of that is still open. What
remains:

- [ ] **O1 — ADK Workflow migration** (blocked on upstream; [ADR-003](docs/ADR-003-adk-workflow-migration.md)).
  `strategies/` still builds on the deprecated `SequentialAgent`,
  `ParallelAgent`, and `LoopAgent` (used in `sequential.py`,
  `parallel.py`, `loop.py`, `evaluator_optimizer.py`, `planner_executor.py`,
  `human_in_loop.py`). ADR-003's gate requires upstream `google.adk` to let
  a `Workflow` act as an `LlmAgent` sub-agent before the swap is possible.
  When the gate is met:
  1. Prototype the four shapes (`sequential`, `parallel`, `loop`,
     `human-in-loop`) behind a strategy-local feature flag.
  2. Run the eight-use-case + example-YAML compatibility matrix with zero
     deprecation warnings.
  3. Keep the legacy path as rollback for one release, then remove it and
     drop the `"ignore:.*is deprecated in favor of Workflow.*"` line from
     `pyproject.toml`'s `filterwarnings`.
- [ ] **O3 — Pin `k8s_agent_sandbox` if adopting `gke` sandbox mode**
  (`pyproject.toml` `gke` extra comment, lines 24–26). The PyPI name/version
  is unverified; executor_type="sandbox" imports it, job mode does not.
  Verify and pin before enabling sandbox mode.
- [ ] **O4 — Re-verify pinned warnings/duties on each `google-adk` upgrade**:
  the `BaseAgentConfig` and `plugins=` deprecation filters in `pyproject.toml`
  (aimed at ADK's own callers), the Workflow-gate status in ADR-003, and the
  verified-internals appendices in ADR-004 A/B (sandbox-image decision,
  docker-py kwargs, socket-proxy ACL semantics).
