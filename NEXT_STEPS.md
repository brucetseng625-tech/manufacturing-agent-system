# Manufacturing Agent System Next Steps

Last updated: 2026-05-09

Current latest completed GitHub commit on `main`:
- `5edb62e` `feat(p12-1): add approval-linked execution handoff`

Latest verified feature commit on `main`:
- `5edb62e` `feat(p12-1): add approval-linked execution handoff`

Latest roadmap sync commit on `main`:
- `0d42b1f` `test(p12-1): add smoke and verify checks for approve-and-retry`
- Full unit test status at handoff: `744 / 744 passed`
- Smoke test status at handoff: `95 / 95 passed`
- Setup verification status at handoff: `148 / 148 passed`
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
- P7 Phase 4 implemented: Safe Fallback and Degraded-Mode Visibility
- New endpoint: `GET /system/degradation-status`
- All providers expose `degradation_status()` with `is_degraded`, `active_path`, `reason`, `recommendations`
- Auto-failover provider detects: live unavailable, circuit breaker open, rollout disabled
- Integration with readiness flags, health diagnostics, rollout controls, and circuit breaker
- P8 Phase 1 implemented: Aggregated System Status Endpoint
- New endpoint: `GET /system/status`
- Aggregated operator-facing view: provider + health + degradation + config + data_dir
- Overall system status: ok/degraded/unhealthy based on health + degradation state
- Server uptime tracking (set at startup)
- P8 Phase 2 implemented: Dashboard Operations Panels
- New 'Ops' navigation view in dashboard
- 4 visual panels: System Status, Health Diagnostics, Degradation Visibility, Data Directory
- Color-coded status badges (green/yellow/red) based on system state
- Degradation reason warning banner and recommendations list

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
- erp data mapping + validation
- readonly provider diagnostics dashboard
- provider selection operator UI
- audit chain for critical operations
- incident report generation
- auto-remediation hooks
- approval workflow dashboard
- approval-linked execution handoff
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
- safe fallback and degraded-mode visibility
- aggregated system status endpoint
- dashboard operations panels
- dry-run execution controls
- alert/notification hooks
- P9 Phase 1 implemented: Alert Acknowledgement Workflow
- Alert lifecycle: `firing` → `acknowledged` → `resolved`
- Unique alert IDs (e.g. `alert-1`, `alert-2`)
- New endpoints: `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve`
- Alert status filtering via `GET /alerts?status=firing`
- Auto-resolve timeout config: `alerts.auto_resolve_seconds`
- P9 Phase 2 implemented: Dashboard Operator Action Panel
- Ops view includes "Operator Actions" card with one-click buttons
- Actions: Reset Alerts, Reload Config, Reload Policy, Health Check
- Inline success/failure feedback via `doAction()` JavaScript
- Dashboard is pure frontend — calls existing API endpoints
- Zero backend changes; additive to dashboard only
- P9 Phase 3 implemented: Incident Timeline View
- Unified timeline aggregating: runs.jsonl (audit), alerts (in-memory), access.log
- New module: timeline.py with build_timeline() and timeline_summary()
- New endpoint: GET /timeline (type filter, last param)
- Dashboard Timeline view with type/limit filters
- Events sorted newest-first with run_id and alert_id badges
- Read-only surface — no mutation of existing log layers
- P9 Phase 4 implemented: Execution Guardrails
- New module: guardrails.py with check_guardrail() and get_guardrails_status()
- Config-driven allow/deny and approval-required rules
- Guarded operations: alerts:reset, config:reload, policy:reload
- New endpoint: GET /guardrails for visibility
- Approval via X-Approval-Token header
- HTTP 403 with structured error on denial
- By default disabled — zero breaking changes
- P10 Phase 1 implemented: HttpReadonlyProvider (First Real Readonly Provider)
- New class: HttpReadonlyProvider in data_source.py
- Fetches JSON from configurable HTTP endpoints (stdlib urllib only)
- Auto-detected by create_provider() when live_provider.http.base_url is set
- Health check: pings {base_url}{health_path} for connectivity diagnostics
- Read-only — no write capabilities, safe first step toward real data
- Falls back to skeleton LiveDataProvider when not configured
- Integrates with existing circuit breaker, auto-failover, degradation layers
- 19 new tests covering config, load, health, readiness, degradation
- P10 Phase 2 implemented: ERP Data Mapping + Validation
- New module: data_mapper.py with SchemaMapper, SchemaValidator, apply_mapping
- Configurable field mapping, type coercion, default values, and validation
- Auto-applied by HttpReadonlyProvider when data_mapping.enabled is true
- Supports orders and materials datasets with configurable rules
- GET /mapping/diagnostics endpoint for operator visibility
- 43 new tests covering coercion, mapping, validation, pipeline, diagnostics
- P10 Phase 3 implemented: Readonly Provider Diagnostics Dashboard
- Dashboard Ops view now includes Readonly Provider Diagnostics card
- Displays provider type, readiness, health, active path, HTTP endpoint URL
- Shows sub-provider details in auto mode (live + fallback readiness)
- Data mapping status badge with per-dataset coverage and runtime stats
- Fetches /system/status and /mapping/diagnostics in parallel for real-time data
- Pure frontend change — no backend modifications required
- 3 smoke test checks + 4 verify setup checks added
- P10 Phase 4 implemented: Provider Selection Operator UI
- Dashboard Ops view now includes Provider Selection card with radio buttons
- Supports switching between local, http, and auto modes at runtime
- POST /provider/select endpoint with guardrail integration
- set_default_provider and get_default_provider_mode added to data_source.py
- /system/status now includes default_mode in provider status
- guardrails updated with provider:select (approval-required by default)
- 7 new unit tests for provider selection API + 4 smoke + 7 verify checks
- Updated README.md, NEXT_STEPS.md, config.example.json
- P11 Phase 1 implemented: Audit Chain for Critical Operations
- New module: audit_chain.py with append_audit_entry, query_audit_log, get_audit_summary
- Unified JSONL audit log for operator actions (logs/audit.jsonl)
- Integrated into config reload, policy reload, provider select, alerts reset, guardrails
- GET /audit endpoint with action/result filters and summary aggregation
- 15 unit tests covering append, query, filter, paginate, summary
- +1 smoke test + 7 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P11 Phase 2 implemented: Incident Report Generation
- New module: incident_report.py with generate_incident_report
- Aggregates system status, alerts, audit entries, timeline into unified report
- GET /incident/report endpoint with configurable time window
- Includes incident summary, affected provider info, resolution status, recommendations
- 22 unit tests covering report structure, helpers, filtering
- +2 smoke test checks + 4 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P11 Phase 3 implemented: Auto-Remediation Hooks
- New module: auto_remediation.py with evaluate_hooks, get_remediation_status, reset_remediation_state
- Config-driven, opt-in (disabled by default)
- Supported triggers: circuit_breaker_open, system_unhealthy, degradation_detected, provider_degraded
- Supported actions: alerts:reset, config:reload, policy:reload, provider:fallback (read-only)
- Per-hook cooldown prevents action spam; dry-run mode for safe testing
- All executions logged to audit chain
- Integrated with alert.py — triggers when alerts fire
- GET /auto-remediation/status, POST /auto-remediation/evaluate, POST /auto-remediation/reset
- 25 unit tests covering config, evaluation, cooldown, status, reset, actions
- +2 smoke test checks + 8 verify setup checks
- Updated README.md, NEXT_STEPS.md, config.example.json
- P11 Phase 4 implemented: Approval Workflow Dashboard
- New module: approval_queue.py — in-memory approval queue with max history
- When guardrails require approval but no token is provided, a pending item is created
- Operators can view, approve, or reject items from dashboard Approval Queue panel
- GET /approvals (with status filter and limit), POST /approvals/{id}/approve, POST /approvals/{id}/reject, POST /approvals/reset
- _check_guardrail_with_queue helper integrates guardrail checks with queue creation
- All state transitions (created, approved, rejected) logged to audit chain
- Dashboard: renderApprovalQueueCard() in Ops view with approve/reject buttons
- 23 unit tests covering queue ops, approvals, stats, reset, token lookup
- +2 smoke test checks + 10 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P12 Phase 1 implemented: Approval-Linked Execution Handoff
- approval_queue.py extended with original_request storage
- POST /approvals/{id}/approve-and-retry endpoint replays blocked operations
- Guardrail handlers capture request body before denying
- Dashboard: approve & retry button for one-click approval + execution
- _replay_request() helper auto-injects approval token for re-execution
- 3 new unit tests for original_request storage
- Updated README.md, NEXT_STEPS.md (P12 roadmap section added)
- P8 Phase 4 implemented: Alert/Notification Hooks
- `alert.py` module with AlertManager for state change detection
- Webhook-based notifications for degraded/unhealthy/critical states
- Three alert types: system_unhealthy (critical), circuit_breaker_open (warning), degradation_detected (warning)
- Cooldown logic prevents alert spam (default 300s)
- New endpoints: `GET /alerts/log`, `POST /alerts/reset`
- Config-driven: `alerts.enabled`, `alerts.webhook_url`, `alerts.cooldown_seconds`
- Integrated with `/system/status` — alerts checked on each status evaluation
- Alerts disabled by default; no webhook calls when `alerts.enabled: false`
- P8 Phase 3 implemented: Dry-Run Execution Controls
- `POST /run` and `POST /batch` now support `dry_run: true` flag
- Dry-run validates request, extracts orders, previews routing — no side effects
- No skill execution, no Asana posting, no audit log writes in dry-run mode
- Response includes: matched skill/team, order_ids, intent, steps

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
| ~~P7~~ | ~~Safe fallback and degraded-mode visibility~~ | ~~Make degraded operation explicit and supportable~~ | ~~Fallback visibility, degraded status surfacing, tests~~ | ~~Health checks + rollout controls~~ | ~~Codex~~ |

## P8 Operations Visibility & Execution Controls

Goal: Provide aggregated operator-facing visibility and safe execution controls for production use.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P8~~ | ~~System status endpoint~~ | ~~Single operator-facing aggregated system view~~ | ~~`/system/status`, tests~~ | ~~P7 complete~~ | ~~Codex~~ |
| ~~P8~~ | ~~Dashboard ops panels~~ | ~~Show health, degradation, provider status on dashboard~~ | ~~Dashboard panels, tests~~ | ~~System status endpoint~~ | ~~Codex~~ |
| ~~P8~~ | ~~Query execution controls~~ | ~~Safe dry-run mode for /run and /batch~~ | ~~`dry_run` flag, tests~~ | ~~Stable /run contract~~ | ~~Codex~~ |
| ~~P8~~ | ~~Alert/notification hooks~~ | ~~Automated alerts on degradation events~~ | ~~Webhook config, tests~~ | ~~Degradation visibility~~ | ~~Codex~~ |

## P9 Incident Management & Operator Actions

Goal: Close the loop on alert lifecycle and provide operator-facing controls for day-2 operations.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P9~~ | ~~Alert acknowledgement workflow~~ | ~~Track alert lifecycle: firing → acknowledged → resolved~~ | ~~Alert IDs, status tracking, lifecycle endpoints, tests~~ | ~~P8-4 alert hooks~~ | ~~Codex~~ |
| ~~P9~~ | ~~Dashboard operator action panel~~ | ~~Buttons: reset alerts, reload config, reload policy, health check~~ | ~~Ops view action card, doAction JS, tests~~ | ~~P9-1~~ | ~~Codex~~ |
| ~~P9~~ | ~~Incident timeline view~~ | ~~Unified event stream: runs, alerts, access log~~ | ~~timeline.py, /timeline endpoint, dashboard view, tests~~ | ~~P9-1~~ | ~~Codex~~ |
| ~~P9~~ | ~~Execution guardrails~~ | ~~Config-driven allow/deny + approval for mutation ops~~ | ~~guardrails.py, /guardrails endpoint, tests~~ | ~~P9-1~~ | ~~Codex~~ |

## P10 Real Readonly Provider Readiness

Goal: Replace skeleton LiveDataProvider with concrete readonly integrations, enabling real data connectivity before moving to writable operations.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P10~~ | ~~HttpReadonlyProvider~~ | ~~Fetch JSON from configurable HTTP endpoints~~ | ~~HttpReadonlyProvider class, health check, tests~~ | ~~P9 complete~~ | ~~Codex~~ |
| ~~P10~~ | ~~ERP data mapping + validation~~ | ~~Map ERP response fields to internal schema~~ | ~~data_mapper.py, field mapper, validation, tests~~ | ~~P10-1~~ | ~~Codex~~ |
| ~~P10~~ | ~~Readonly provider diagnostics dashboard~~ | ~~Show HTTP provider health, latency, error rates~~ | ~~Dashboard card, smoke/verify checks~~ | ~~P10-1~~ | ~~Codex~~ |
| ~~P10~~ | ~~Provider selection operator UI~~ | ~~Let operator switch between local/http/auto from dashboard~~ | ~~Dashboard card, POST /provider/select, guardrails, tests~~ | ~~P10-1, P9-2~~ | ~~Codex~~ |

## P11 Operator Governance & Audit

Goal: Deepen approval/audit chain, incident reporting, and limited automation safety.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| ~~P11~~ | ~~Audit chain for critical operations~~ | ~~Unified audit log for operator actions~~ | ~~audit_chain.py, /audit endpoint, integration, tests~~ | ~~P10 complete~~ | ~~Codex~~ |
| ~~P11~~ | ~~Incident report generation~~ | ~~Auto-generate reports from timeline + audit + alerts~~ | ~~incident_report.py, /incident/report endpoint, tests~~ | ~~P11-1~~ | ~~Codex~~ |
| ~~P11~~ | ~~Auto-remediation hooks~~ | ~~Config-driven safe auto-fix on alert triggers~~ | ~~auto_remediation.py, endpoints, cooldown, tests~~ | ~~P11-1~~ | ~~Codex~~ |
| ~~P11~~ | ~~Approval workflow dashboard~~ | ~~Visual approval queue for guarded operations~~ | ~~approval_queue.py, dashboard panel, endpoints, tests~~ | ~~P11-1, P9-4~~ | ~~Codex~~ |

## P12 Limited Automation Actions

Goal: Bridge the gap between approval and execution, enabling safe limited automation with full audit traceability.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P12 | ~~Approval-linked execution handoff~~ | ~~Re-execute blocked operations after approval~~ | ~~approve-and-retry endpoint, original request capture, dashboard retry button~~ | ~~P11-4~~ | ~~Codex~~ |
| P12 | Automation policy controls | Config-driven severity tiers for auto-remediation | severity levels, risk-based cooldowns, tests | P11-3 | Codex |
| P12 | Rollback & audit visibility | Track auto-actions with rollback capability | rollback log, audit trail enhancement, tests | P12-1, P11-1 | Codex |

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
| ~~8~~ | ~~Safe fallback and degraded-mode visibility~~ | ~~Make degraded live behavior visible and operable~~ |

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
P12 roadmap defined. P12-1 (Approval-linked execution handoff) complete. Next: P12-2 (Automation policy controls).

Requirements:
- Reuse the existing routing, schema, team execution, API, provider, policy, deployment, and observability layers instead of replacing them
- Do not re-open completed P4 work unless a new blocking issue is found
- Keep the unified schema, history, dashboard, CLI output, and Asana formatting behavior compatible
- Prefer minimal, incremental changes
- Add tests
- Update README and NEXT_STEPS.md if needed
- Run tests and report results
```
