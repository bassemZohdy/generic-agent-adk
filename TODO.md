# TODO — Use-Case Reclassification & Runtime Consolidation

**Status**: ✅ Complete (all phases) · **Completed**: 2026-08-14
**Code root**: `src/basic_agent/` (root-level report MDs reference stale `basic_agent/` paths)

## Goal

Reclassify the agent selection surface from tech patterns (EVALUATOR_OPTIMIZER, PLANNER_EXECUTOR, …)
to **generic use cases** users actually mean ("refine output until good", "route to experts"),
consolidate the two parallel orchestration systems into one, and make mounted YAML actually work
(today it is silently ignored — runtime is env-only via `agent.py:root_agent`).

## Locked decisions (recorded in ADR-002 during Phase 6)

1. **Dual-layer abstraction, one-way dependency** (`use_cases` → `strategies`, never reverse):
   - `strategies/` internal: how the ADK tree is shaped. Deepened with shared `llm()` builder + per-role config.
   - `use_cases/` public: what the user picks + runtime behavior via hooks. Metadata lives ONLY here.
2. `BaseUseCaseAgent` is a **facade owning an ADK tree** (not an `Agent` subclass — multi-agent
   shapes can't single-inherit). Freedom = overriding hooks or swapping strategy.
3. **Hooks map 1:1 to ADK callbacks**; only overridden hooks are wired (no default callback overhead).
4. **Config merge rule**: YAML base (auto-detected `/app/config/agent.yaml` or `AGENT_CONFIG_FILE`,
   `${VAR:default}` substitution runs first) → env override pass (ONLY the 7 documented vars, ONLY if
   explicitly set) → no file → env-only builder → `validate()` → registry → build. One provenance log line.
5. Old names (`AGENT_PATTERN`, `agent.type`, `AGENT_PATTERN_*`) = deprecated aliases, one release.
   Per-role instructions are YAML-only; env sets role NAMES only.

## Reference: use-case taxonomy

| Use case key | User intent | Strategy (internal) |
|---|---|---|
| `assistant` | simple Q&A, one-shot | DIRECT |
| `research_assistant` | searches/investigates with tools | REACT |
| `pipeline` | fixed steps: fetch → analyze → summarize | SEQUENTIAL |
| `multi_perspective` | several independent takes, aggregated | PARALLEL |
| `refine_until_good` | improve output until quality bar | EVALUATOR_OPTIMIZER (LOOP = bounded variant) |
| `expert_dispatch` | question types → specialists | ROUTER |
| `team_coordinator` | delegate complex work to workers | SUPERVISOR |
| `plan_and_execute` | split big task: plan then execute | PLANNER_EXECUTOR |
| `approval_gate` | risky actions need my sign-off | HUMAN_IN_LOOP |

Alias map: `generic`→`assistant`, `direct`→`assistant`, `react`→`research_assistant`,
`sequential`→`pipeline`, `parallel`→`multi_perspective`, `loop`/`evaluator_optimizer`→`refine_until_good`,
`router`→`expert_dispatch`, `supervisor`→`team_coordinator`, `planner_executor`/`plan_execute`→`plan_and_execute`,
`human_in_loop`→`approval_gate`. (Uppercase variants of all aliases also resolve.)

## Reference: minimal env surface

| Var | Required | Default | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | via YAML `${VAR}` substitution when file present |
| `AGENT_USE_CASE` | — | `assistant` | replaces `AGENT_PATTERN` (alias kept) |
| `ADK_MODEL` | — | `gemini-3.6-flash` | |
| `AGENT_INSTRUCTION` | — | generic prompt | |
| `AGENT_TOOLS` | — | all tools | comma-separated |
| `AGENT_MAX_ITERATIONS` | — | `3` | alias: `AGENT_PATTERN_MAX_ITERATIONS` |
| `AGENT_SPECIALISTS` | — | `research,solution,risk` | names must match YAML role keys if roles present |

---

## Phase 1 — Deepen strategy layer · commit A (invisible to users)

- [x] T1.1 **Role config on RuntimeContext** — done 2026-08-14 (delegated, reviewed; suite 103→green)
- [x] T1.2 **Shared `llm()` builder on AgentStrategy** — done 2026-08-14
- [x] T1.3 **Rewrite 10 strategies to use `llm()`; fix router bug** — done 2026-08-14 (distinct specialist instructions verified)
- [x] T1.4 **Type-specific validation moves into strategies** — done 2026-08-14 (loader structural-only; coverage moved to strategy tests)

## Phase 2 — `use_cases/` package · commit B/1 (the switch)

- [x] T2.1 **`BaseUseCaseAgent` facade** — done 2026-08-14 (hook wiring verified against ADK 2.6.3 unified Context signatures)
- [x] T2.2 **Nine declarative subclasses** — done 2026-08-14 (approval_gate.before_tool veto + multi_perspective.after_run aggregation)
- [x] T2.3 **Use-case registry** — done 2026-08-14 (alias/case-insensitive, catalog errors)
- [x] T2.4 **Custom use-case registration** — done 2026-08-14 (`load_custom_use_cases` + env-driven)

## Phase 3 — Runtime wiring · commit B/2 (includes T5.1/T5.2 — loader changes are a hard dependency of the wiring; pulled into the same delegation)

- [x] T3.1 **Config resolution pipeline in `agent.py`** — done 2026-08-14 (`resolve_agent_config()` → RuntimeContext → registry → build; patterns import removed; module contract intact)
- [x] T3.2 **`apply_env_overrides()` + provenance log** — done 2026-08-14 (7 vars + deprecated alias chain; explicit-but-missing `AGENT_CONFIG_FILE` fails fast)
- [x] T3.3 **Specialists/roles consistency guard** — done 2026-08-14 (set-equality check, names both sets in error)

## Phase 4 — Delete `patterns/` · commit C

- [x] T4.1 Remove `src/basic_agent/patterns/` — done 2026-08-14 (dir deleted; swap removed in Phase 3; grep clean; `AgentPattern` enum retained in config.py as deprecated-alias validator)
- [x] T4.2 Sweep deploy surfaces — done 2026-08-14 (docker-compose ×4 blocks + ci.yml → `AGENT_USE_CASE`; grep clean)

## Phase 5 — Config surfaces

- [x] T5.1 **YAML `agent.use_case` primary** — done 2026-08-14 (in Phase 3 delegation; `agent.type` alias, `roles:` section)
- [x] T5.2 **Env-only builder speaks use cases** — done 2026-08-14 (call-time env reads, deprecated fallbacks with warnings)
- [ ] T5.3 **`.env.example` reorganized** — minimal 7-var block top, YAML pointer below,
  deprecation notes.
  *Done when: nothing required beyond GOOGLE_API_KEY for default run.*

## Phase 6 — Examples + docs · commit D

- [x] T6.3 **README use-case-first** — DONE FIRST (user request, 2026-08-14): decision table,
  env/YAML reference, merge semantics, deprecation table. Documents target state — re-verify
  claims after Phase 3 lands.
- [x] T6.1 **Examples renamed to use cases** — done 2026-08-14 (9 files; parametrized load+build test ×9)
- [x] T6.2 **`expert-dispatch.yaml` demonstrates `roles:`** — done 2026-08-14 (billing/technical/general, one model override)
- [x] T6.4 **ADR-002** — done 2026-08-14 (`docs/ADR-002-use-case-taxonomy.md`)
- [x] T6.5 **Archive stale reports** — done 2026-08-14 (13 files → `docs/archive/`)

## Phase 7 — Tests

- [x] T7.1 Update `tests/test_strategies.py` — done 2026-08-14 (Phase 1: llm()/roles/validation, 19 tests)
- [x] T7.2 Update `tests/test_config_loader.py` — done 2026-08-14 (Phase 3: 27 tests incl. overrides/aliases/guard/provenance)
- [x] T7.3 Update `tests/test_integration_strategies.py` — done 2026-08-14 (examples loop ×9 added in Phase 6)
- [x] T7.4 Update `tests/test_agent.py` — done 2026-08-14 (Phase 3; patterns tests removed in Phase 4)
- [x] T7.5 New: hook wiring, approval veto, aggregation hook — done 2026-08-14 (Phase 2: tests/test_use_cases.py, 25 tests)
- [x] T7.6 New: custom-module registration via `AGENT_USE_CASE_MODULE` — done 2026-08-14 (Phase 2 + T8.8 container proof)

## Phase 8 — Verification & smoke (Definition of Done)

- [x] T8.1 `uv run pytest` — full suite green (169 tests)
- [x] T8.2 `docker build` OK; no-config container starts as `assistant` (provenance: `yaml=none`)
- [x] T8.3 Mounted-YAML smoke ×3 — research_assistant (react_agent) / expert_dispatch (3 role
  specialists) / approval_gate (proposer+completer); all `source: yaml`
- [x] T8.4 Env-only smoke — `AGENT_USE_CASE=refine_until_good` → LoopAgent, `source: env`
- [x] T8.5 Back-compat — `AGENT_PATTERN=sequential` → `pipeline` SequentialAgent, deprecation warning logged once
- [x] T8.6 Merge — mounted YAML + `ADK_MODEL` → provenance `env overrides: ADK_MODEL`, yaml source retained
- [x] T8.7 Runtime hooks — approval_gate veto unit-tested; expert_dispatch specialists show DISTINCT
  role instructions in built tree (verified in container)
- [x] T8.8 Custom module — `AGENT_USE_CASE_MODULE` registered `support_triage` and built it in container

**ALL PHASES COMPLETE — 2026-08-14.**

## Post-completion cleanup — 2026-08-14 (docs / CI / tests refresh)

- [x] README badges: 169 tests / 88% coverage, links point to `tests/` (report now in `docs/archive/`)
- [x] ADR-001: superseded-by-ADR-002 banner (body kept as historical record)
- [x] `.github/PUBLISHING.md` + `.github/CI-CD-INTEGRATION.md`: `react-agent.yaml` →
  `research-assistant.yaml`, `AGENT_PATTERN: react` → `AGENT_USE_CASE: research_assistant`,
  test-count refresh
- [x] `ci.yml` verify-image: startup smoke now ASSERTS (assistant→direct_agent; mounted
  approval-gate.yaml→SequentialAgent) instead of `|| true` print; notify message fixed
- [x] Broken-link sweep of active docs: clean (archive excluded intentionally)
- [x] CI parity checks local: `git diff --check` ✓, realm JSON ✓, `docker compose config` ✓,
  workflow YAML parses ✓, both new CI smoke assertions pass against built image ✓
- [x] Final gate: 169 passed, coverage 88.23% ≥ 85 threshold ✓

Remaining housekeeping: commits A–D (see sequencing); working tree also holds pre-existing
`src/` layout + docs moves to commit first.

## Improvement round 2 — 2026-08-14 (providers / interfaces / consolidation)

- [x] **Multi-provider LLM** — `src/basic_agent/models.py` `resolve_model()`: Gemini native,
  any `provider/model` prefix (openai, anthropic, ollama, groq, deepseek, mistral, vllm, …)
  via ADK LiteLlm; `ModelConfig.base_url`; api_key/base_url passthrough; provider env hints
  with warn-once; `litellm` dependency added. Verified: `openai/gpt-4o` YAML + env builds
  LiteLlm root agent locally and in container (construction-only, no network).
- [x] **Interfaces metadata** — `interfaces` attr on use cases (rest/web/cli default; `live`
  on assistant), exposed in `list_use_cases()` catalog; README Interfaces section. Verified:
  `adk api_server` serves docs 200 + app registered in container.
- [x] **Use-case consolidation 9 → 8** — `research_assistant` merged into `assistant`
  (DIRECT and REACT strategies build identical agents; behavior differs only by tools
  enabled); `research_assistant`/`react` kept as aliases; example file repurposed
  tools-forward. Kept separate (documented in ADR-002 addendum): expert_dispatch vs
  team_coordinator, pipeline vs plan_and_execute.
- [x] **Bug found & fixed** — `AGENT_PATTERN` enum rejected legacy `react`/`direct`/
  `supervisor`/`plan_execute` names that `agent.type` YAML always accepted; enum completed;
  container-verified `AGENT_PATTERN=react → assistant`.
- [x] Gate: 182 passed; docker rebuilt; smokes green. ADR-002 addendum records all three.

## Improvement round 3 — 2026-08-15 (project review: security / correctness / hardening)

Source: full code-review + security audit (182 tests green at time of review). Priority order = recommended attack order.

### P0 — Critical (close pre-auth paths first)

- [ ] **R1. Remove Keycloak realm backdoor** — `keycloak/realm-basic-agent.json:25-35`: `demo`/`demo`
  user with `agent-operator` role, public client + `directAccessGrantsEnabled`, Keycloak admin
  password defaulting to `admin` (`docker-compose.yml:21-25`). Gate demo user behind a dev profile
  (`DEMO_MODE`), disable direct grants outside dev, require `KEYCLOAK_ADMIN_PASSWORD` (no default),
  enable `bruteForceProtected`.
- [ ] **R2. Fail-closed auth** — `src/basic_agent/auth.py:63-64, 81-82`: unset `KEYCLOAK_ISSUER`
  silently disables all auth; `deploy/cloudrun/service.yaml` omits it entirely. Require explicit
  `AUTH_DISABLED=true` opt-in; fail startup in prod `DEPLOYMENT_ENV`; add Cloud Run ingress
  annotation + IAM.
- [ ] **R3. Bind user identity to token subject (IDOR)** — `src/basic_agent/live_server.py:88-95`:
  JWT claims discarded, `user_id`/`session_id` from query params → cross-user session access. Same
  pattern via `adk api_server --auto_create_session` accepting arbitrary `user_id` in body. Derive
  `user_id` from `claims["sub"]`; bind session ownership; middleware for REST layer.
- [ ] **R4. Locked Docker builds** — `Dockerfile:12-13` uses `pip install .`, ignores `uv.lock`,
  floor-only `>=` constraints → non-reproducible images (A05 supply chain). Switch to
  `COPY uv.lock` + `uv sync --frozen --no-dev`; add CI check that image deps match lock; add
  `pip-audit`/trivy scan.
- [ ] **R5. Remove broken entry point** — `pyproject.toml:16` `generic-agent-eval` references
  nonexistent `basic_agent.evaluation` module. Create the module or delete the script entry.

### P1 — High

- [ ] **R6. ADK Workflow migration spike** — strategies build on deprecated `SequentialAgent` /
  `ParallelAgent` / `LoopAgent` (deprecation warnings across `strategies/`); plan migration before
  upstream removal.
- [ ] **R7. Kill import-time side effects** — `agent.py:311-312` (config resolution + agent build at
  import) and `agent.py:154-161` (MCP/OpenAPI toolsets constructed unconditionally). Lazy
  factories/guarded build.
- [ ] **R8. Service API-key path** — `auth.py:70-71`: documented default `local-service-key`
  bypasses `require_roles`; non-constant-time `==` compare. No default (fail closed),
  `secrets.compare_digest`, apply role checks to this path.
- [ ] **R9. WS token out of query string** — `auth.py:86` `access_token` query param leaks into
  proxy/access logs; use subprotocol or first-message auth.
- [ ] **R10. Audience verification on by default** — `auth.py:32` `verify_aud` only when
  `KEYCLOAK_AUDIENCE` set (empty default); any realm client's token accepted. Default to client id.
- [ ] **R11. Cache JWKS client** — `auth.py:24` new `PyJWKClient` per request → per-request
  Keycloak fetch (latency + DoS amplifier). Module-level instance + fetch timeout.
- [ ] **R12. `execution.steps`/`workers` wired** — parsed in `config_loader.py:509-515` but never
  forwarded to strategies (`agent.py:278-298`); sequential/parallel always build 2. Forward via
  `extra_config`; add int validation in strategies.

### P2 — Medium

- [ ] **R13. Prompt-injection hardening** — wrap retrieved knowledge/search content
  (`agent.py:105-121, 184-191`) in untrusted-data framing; drop `code_execution` from default
  `AGENT_TOOLS`; scope OpenAPI toolset off the service credential; require approval for any
  state-mutating tool.
- [ ] **R14. Rate limits + WS payload caps** — `live_server.py:116-130` unbounded `receive_json` /
  base64 audio, each message = LLM call; add max size + msg/sec budget, Traefik rate-limit
  middleware, per-token spend quotas.
- [ ] **R15. Container hardening** — non-root `USER`, resource limits in compose,
  uvicorn `--limit-concurrency`; socket-proxy for Traefik's docker.sock; bind Grafana/OTLP to
  `127.0.0.1`, override default creds; disable FastAPI `/docs` in prod.
- [ ] **R16. Audit logging** — record `sub` + roles per request (`service_api.py:29`,
  `live_server.py:88` currently discard claims); log every tool invocation (identity + outcome).
- [ ] **R17. Config error UX** — friendly `ValueError` for non-int `AGENT_MAX_ITERATIONS`
  (`config.py:103`, `config_loader.py:509-511`, `AGENT_KNOWLEDGE_RESULT_LIMIT`); allow subset
  specialists or document set-equality (`config_loader.py:418`); refuse unresolved `${VAR}` in
  YAML; gitleaks pre-commit.
- [ ] **R18. Settings test seam** — replace ~15 `object.__setattr__(settings, …)` hacks on frozen
  dataclass with snapshot/restore autouse fixture or `reload_settings()`.
- [ ] **R19. Auth-path cleanup** — remove redundant double check `service_api.py:32`; include
  error reason in WS close `live_server.py:87-91`; handle multi-audience tokens (`auth.py:32`);
  drop `X-Auth-Email` response header (`auth_gateway.py:32-33`).
- [ ] **R20. Misc code health** — relative import in `mcp_server.py:8`; share Runner across WS
  connections (`live_server.py:97-102`); log swallowed exceptions in `multi_perspective.py:31` /
  `approval_gate.py:38`; mtime-cache knowledge file reads (`agent.py:93-102`); UUID module names
  in custom registry (`use_cases/registry.py:152`); docs/API key allowlisting for
  `AGENT_USE_CASE_MODULE`.

### Tests to add alongside

- [ ] **R-T1.** Auth regression: HS256-confusion token → 401; wrong-issuer token → 401; API-key
  path enforces roles; issuer unset + prod env → startup failure (after R2).
- [ ] **R-T2.** IDOR: subject A resuming subject B's `user_id`/`session_id` → rejected (after R3).
- [ ] **R-T3.** Supply chain: CI asserts `pip freeze` in built image matches `uv.lock` (after R4).
- [ ] **R-T4.** Prompt-injection corpus in knowledge file asserting no openapi/mcp tool calls from
  injected instructions (after R13); WS oversized-frame fuzz (after R14).

## Commit / rollback sequencing

| Commit | Contents | Reverts |
|---|---|---|
| A | Phase 1 (invisible deepening) | cleanly, no behavior change |
| B | Phases 2–3 (use_cases + wiring — the switch) | cleanly without touching A |
| C | Phase 4 (deletion) | trivially (files restored) |
| D | Phases 5–6 (surfaces + docs) | docs-only risk |

## Out of scope (explicit)

- Per-role instructions via env vars (flat env can't express structure; YAML-only)
- Removing deprecated aliases (one full release after D ships)
- Any UI (registry catalog is UI-ready; no UI built now)
- Rewriting archived reports
