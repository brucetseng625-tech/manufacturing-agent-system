# Manufacturing Agent System Next Steps

Last updated: 2026-05-08

Current latest completed GitHub commit on `main`:
- `7c1dd31` `feat(p7): add per-provider rollout controls`

Latest verified feature commit on `main`:
- `7c1dd31` `feat(p7): add per-provider rollout controls`

Latest roadmap sync commit on `main`:
- `7c1dd31` `feat(p7): add per-provider rollout controls`
- Full unit test status at handoff: `455 / 455 passed`
- Smoke test status at handoff: `42 / 42 passed`
- Setup verification status at handoff: `60 / 60 passed`
- Working tree at handoff: clean

Accepted P4 completion context:
- `016a200` `feat: implement configurable rules / policy layer`
- `09cb43c` `feat: add deployment readiness — runbook, smoke tests, setup verification`
- `c424f82` `feat: add observability and traceability — run IDs, structured logs, Asana trace linking`
- Full unit test status at handoff: `301 / 301 passed`
- Smoke test status at handoff: `30 / 30 passed`
- Setup verification status at handoff: `42 / 42 passed`
- Working tree at handoff: clean

Current post-P4 follow-up:
- Additional planning refinements implemented as an integrated recovery planning team workflow
- New team workflow: `team:recovery-planning`
- Scope: bundle shortage recovery, expedite options, capacity rebalance, and supplier follow-up into one coordinated planning entrypoint
- P5 Phase 1 implemented: Metrics API + Dashboard Stats
- New endpoint: `GET /metrics`
- Dashboard now includes stats cards and skill distribution visualization
- P5 Phase 2 implemented: Batch Query Support
- New endpoint: `POST /batch`
- CLI now supports `--batch-file` for multi-query execution
- P5 Phase 3 implemented: Policy Hot-Reload
- New endpoint: `POST /policy/reload`
- CLI now supports `--reload-policy` for immediate policy refresh
- P5 Phase 4 implemented: Data Dir Auto-Reload
- New endpoint: `GET /data/status`
- CLI now supports `--data-dir-status` for directory change visibility
- P6 Phase 1 implemented: Config Management Layer
- P6 Phase 2 implemented: API Token Auth
- New endpoints protected: POST /run, /batch, /config/reload, /policy/reload
- Supports Authorization: Bearer and X-API-Token headers
- Dev mode preserved when no token configured
- P6 Phase 3 implemented: Circuit Breaker for Live Provider
- CircuitBreaker class with closed/open/half_open states
- Config-driven via live_provider.circuit_breaker (failure_threshold + recovery_seconds)
- AutoFailoverProvider uses circuit breaker in auto mode
- Recovery probing after timeout allows live source reconnection
- P6 Phase 4 implemented: Server Access Logging
- Structured JSONLines access log at logs/access.log
- Records timestamp, method, path, status_code, duration_ms, client, run_id
- Config-driven via logging.access_log (MAS_ACCESS_LOG env)
- Thread-safe file writes with flush
- P7 Phase 1 implemented: Provider Capability Registry + Readiness Flags
- New endpoint: `GET /provider/status`
- ProviderCapability enum: read, write, health_check
- ProviderReadiness enum: ready, not_configured, degraded, disabled, circuit_open
- Provider status now exposes readiness, capabilities, and auto-failover sub-provider details
- P7 Phase 2 implemented: Live Provider Health Check and Diagnostics
- New endpoint: `GET /provider/health`
- All providers now expose a unified `health_check()` contract
- Auto-failover health aggregates live, fallback, and circuit-breaker state
- Health states include ok, unreachable, not_configured, degraded, circuit_open, unhealthy
- P7 Phase 3 implemented: Per-Provider Rollout Controls
- Config-driven rollout gates: `rollout.local.enabled`, `rollout.live.enabled`, `rollout.auto.enabled`
- Environment overrides: `MAS_ROLLOUT_LOCAL_ENABLED`, `MAS_ROLLOUT_LIVE_ENABLED`, `MAS_ROLLOUT_AUTO_ENABLED`
- Disabled providers report `disabled` readiness, `is_available=False`, health status `disabled`
- Works seamlessly with readiness flags, health diagnostics, and circuit breaker
- Zero breaking changes to existing CLI, API, history, metrics, dashboard, auth, access logging
- New endpoints: `GET /config`, `POST /config/reload`
- CLI now supports `--show-config` for centralized config inspection

Current completed scope:
- delivery-risk-analysis
- schedule-conflict-check
- data loader JSON/CSV
- data validation
- Asana integration
- audit log
- Skill Registry / Agent Teams skeleton
- quote-comparison-summary
- sales-response-draft
- internal-action-summary
- Asana workflow enhancement
- output schema unification
- query routing improvement
- Agent Teams MVP
- run history query support
- API enhancement
- error handling hardening
- data model expansion
- quote comparison enhancement
- parallel team execution
- web dashboard mvp
- MCP / ERP integration layer
- expedite-options skill
- material-shortage-recovery skill
- capacity-rebalance skill
- supplier-followup-draft skill
- configurable rules / policy layer
- deployment readiness
- observability and traceability
- recovery planning team workflow
- metrics api + dashboard stats
- batch query support
- policy hot-reload
- data dir auto-reload
- config management layer
- api token auth
- circuit breaker for live provider
- server access logging
- provider capability registry + readiness flags
- live provider health check and diagnostics
- per-provider rollout controls

## P5 Productionization / Live Integration Planning

Goal: Move from mock-data-first prototype toward real internal use without major architecture changes.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P5~~ | ~~Metrics API + Dashboard Stats~~ | ~~Ops visibility into system usage and health~~ | ~~Endpoint, Dashboard panel, tests~~ | ~~Audit log available~~ | ~~Codex~~ |
| ~~P5~~ | ~~Batch Query Support~~ | ~~Process multiple orders in one request~~ | ~~Batch endpoint, CLI --batch-file, tests~~ | ~~Stable /metrics~~ | ~~Codex~~ |
| ~~P5~~ | ~~Policy Hot-Reload~~ | ~~Adjust thresholds without restart~~ | ~~Reload endpoint, CLI flag, metadata, tests~~ | ~~Policy layer stable~~ | ~~Codex~~ |
| ~~P5~~ | ~~Data Dir Auto-Reload~~ | ~~Detect CSV/JSON drops without restart~~ | ~~Status endpoint, CLI flag, mtime tracking, tests~~ | ~~Provider layer stable~~ | ~~Codex~~ |

## P6 Integration Hardening / Access Control

Goal: Add production-safe configuration and access controls on top of the completed P5 operating surface.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P6~~ | ~~Config management layer~~ | ~~Centralize runtime configuration with file + env override~~ | ~~Loader, config endpoints, CLI view, tests~~ | ~~P5 complete~~ | ~~Codex~~ |
| ~~P6~~ | ~~API token auth~~ | ~~Protect HTTP endpoints~~ | ~~Auth middleware, config integration, tests~~ | ~~Config layer available~~ | ~~Codex~~ |
| ~~P6~~ | ~~Circuit breaker for live provider~~ | ~~Fail safely and recover automatically~~ | ~~Failure threshold, reset window, tests~~ | ~~Provider layer stable~~ | ~~Codex~~ |
| ~~P6~~ | ~~Server access logging~~ | ~~Structured HTTP access log for audit/support~~ | ~~Access log format, request timing, tests~~ | ~~Observability layer available~~ | ~~Codex~~ |

## P7 Live Integration Readiness

Goal: Make provider capabilities, live readiness, and degraded-mode behavior explicit before deeper real-source integration.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P7~~ | ~~Provider capability registry + readiness flags~~ | ~~Expose what each provider can do and whether it is ready~~ | ~~Capability metadata, readiness states, `/provider/status`, tests~~ | ~~P6 complete~~ | ~~Codex~~ |
| ~~P7~~ | ~~Live provider health check and diagnostics~~ | ~~Detect real-source connectivity and failure causes~~ | ~~Health checks, diagnostics output, tests~~ | ~~Provider status available~~ | ~~Codex~~ |
| ~~P7~~ | ~~Per-provider rollout controls~~ | ~~Control exposure of live features by provider~~ | ~~Config gates, rollout flags, tests~~ | ~~Config layer + provider readiness~~ | ~~Codex~~ |
| P7 | Safe fallback and degraded-mode visibility | Make degraded operation explicit and supportable | Fallback visibility, degraded status surfacing, tests | Health checks + rollout controls | Codex |

## Start Here

When a new Codex / AI session starts, do this first:

1. Pull latest `main`
2. Read this file
3. Check `skills/registry.py`, `run_agent.py`, `integrations/asana_client.py`
4. Start with the next unfinished roadmap item, or define the next roadmap phase if everything listed here is complete

## Roadmap Table

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P4~~ | ~~Configurable rules / policy layer~~ | ~~Move decision rules out of hardcoded logic~~ | ~~Rule config structure, loader, tests~~ | ~~Existing skills stable~~ | ~~Codex~~ |
| ~~P4~~ | ~~Deployment readiness~~ | ~~Prepare for actual internal use~~ | ~~Runbook, config docs, server mode validation~~ | ~~API and error handling maturity~~ | ~~Codex~~ |
| ~~P4~~ | ~~Observability and traceability~~ | ~~Make runs easier to audit and support~~ | ~~Run IDs, structured logs, Asana trace linking~~ | ~~Audit log and API available~~ | ~~Codex~~ |

## Suggested Execution Order

| Order | Work Item | Why Now |
| --- | --- | --- |
| ~~1~~ | ~~Configurable rules / policy layer~~ | ~~Best next step now that the major P3 skill surface is complete~~ |
| ~~2~~ | ~~Deployment readiness~~ | ~~Natural follow-on once policy boundaries and runtime expectations are clearer~~ |
| ~~3~~ | ~~Observability and traceability~~ | ~~High leverage after workflow surface has stabilized~~ |
| ~~4~~ | ~~Additional planning refinements~~ | ~~Reserve for future expansion after core platform hardening~~ |
| ~~5~~ | ~~Provider capability registry + readiness flags~~ | ~~Foundation for live integration readiness~~ |
| ~~6~~ | ~~Live provider health check~~ | ~~Diagnostics for production ERP/MCP sources~~ |
| ~~7~~ | ~~Per-provider rollout controls~~ | ~~Config-driven deployment controls~~ |
| 8 | Safe fallback and degraded-mode visibility | Make degraded live behavior visible and operable |

## Ready-To-Use Prompt For The Next AI

```text
Please start with /Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/NEXT_STEPS.md

Repo:
https://github.com/brucetseng625-tech/manufacturing-agent-system

First actions:
1. Pull latest main
2. Read NEXT_STEPS.md
3. Confirm latest completed commit
4. Continue from the next unfinished roadmap item, or define the next roadmap phase if everything listed here is complete

Current expected next task:
P7-3 (Per-provider rollout controls) is complete. Continue with P7-4: Safe fallback and degraded-mode visibility.

Requirements:
- Reuse the existing routing, schema, team execution, API, provider, policy, deployment, and observability layers instead of replacing them
- Do not re-open completed P4 work unless a new blocking issue is found
- Keep the unified schema, history, dashboard, CLI output, and Asana formatting behavior compatible
- Prefer minimal, incremental changes
- Add tests
- Update README and NEXT_STEPS.md if needed
- Run tests and report results
```
