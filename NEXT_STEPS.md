# Manufacturing Agent System Next Steps

Last updated: 2026-05-14

Current latest completed feature commit on `main`:
- `63f9b18` `feat(P16-3): visual asset and scene styling upgrade`

Latest verified feature commit on `main`:
- `63f9b18` `feat(P16-3): visual asset and scene styling upgrade`

Important handoff note:
- `main` may move to a docs-only sync commit after the latest verified feature commit above. Always confirm exact `HEAD` with `git rev-parse HEAD` before continuing.
- Full unit test status at handoff: `919 / 919 passed`
- Smoke test status at handoff: `112 / 112 passed`
- Setup verification status at handoff: `204 / 204 passed`
- Working tree at handoff: clean (after P16-3 commit)

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
- automation policy controls
- rollback & audit visibility
- approval replay preview visibility
- automation execution receipts
|- incident closure workflow
|- pilot readiness checklist
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
- P12 Phase 3 implemented: Rollback & Audit Visibility
- New module: `rollback_eligibility.py` — read-only analysis of audit entry reversibility
- `analyze_entry()` determines rollback eligibility per action type
- `query_rollback_eligibility()` with category/eligible filters + pagination
- `get_rollback_summary()` for high-level statistics
- 10 action-type rules covering guarded_operation, approval_lifecycle, automation categories
- `GET /audit/rollback` endpoint with filtering (category, eligible, last, offset)
- 28 unit tests covering rules, analyze_entry, query, summary
- +2 smoke test checks + 6 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P13 Phase 1 implemented: Approval Replay Preview Visibility
- Approval queue API now returns sanitized `request_preview` metadata for pending/reviewed items
- Sensitive request fields like `approval_token` are redacted from approval list/detail responses
- New endpoint: `GET /approvals/{id}` for operator review of a single approval item
- Dashboard Approval Queue now shows replay request method/path, body summary, and a low/medium risk badge
- 6 new tests covering preview serialization, redaction, single-item endpoint, and dashboard markup
- Updated README.md, NEXT_STEPS.md
- P13 Phase 2 implemented: Automation Execution Receipts
- New module: `execution_receipts.py` with `record_receipt`, `query_receipts`, `get_receipts_summary`, `reset_receipts`
- Unified in-memory capped receipt log for both approval-retry and auto-remediation outcomes
- New endpoints: `GET /automation/receipts` (with source/status/operation filters + summary), `POST /automation/receipts/reset`
- Integrated into approve-and-retry flow — records success/failed/error/skipped/policy_denied receipts
- Integrated into auto_remediation.py — all execution paths (executed/dry_run/cooldown/policy_denied/skipped/error) emit receipts
- All receipts also logged to audit chain for full traceability
- 20 unit tests + 3 smoke checks + 9 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P13 Phase 3 implemented: Incident Closure Workflow
- New module: `incident_closure.py` with `upsert_closure`, `query_closures`, `get_closure`, `reset_closures`
- New endpoints: `GET /incident/closures`, `GET /incident/closures/{report_id}`, `POST /incident/closures/{report_id}`, `POST /incident/closures/reset`
- Supports explicit operator status transitions: `open`, `investigating`, `monitoring`, `resolved`
- Closure records support `resolution_note`, `linked_alert_ids`, and `linked_receipt_ids` for incident linkage
- Incident report payload now includes `closure` so report snapshots can reflect operator-managed closure state
- 12 new unit tests + 3 smoke checks + 8 verify setup checks
- Updated README.md, NEXT_STEPS.md
- P13 Phase 4 implemented: Pilot Readiness Checklist
- New module: `pilot_checklist.py` with `get_checklist`, `get_checklist_summary`
- 11 checklist items across 3 categories: Safety (SC-01 to SC-03), Observability (OB-01 to OB-04), Workflow (WF-01 to WF-04)
- GET /pilot/checklist endpoint — returns items + summary with `all_ready` flag
- Pure read-only aggregation — queries live system surfaces (circuit breaker, alerts, audit chain, receipts, closures, provider, guardrails, rollback)
- 18 unit tests + 3 smoke checks + 10 verify setup checks
- Updated README.md, NEXT_STEPS.md
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

## P14 Limited Rollout Readiness

Goal: Move from operator pilot readiness to production pilot / limited rollout readiness. Enable controlled rollout with explicit gating, approval, and rollback surfaces.

### P14-1 Rollout Gating Profile (completed)

- New module: `rollout_profile.py` with `get_rollout_profile`, `get_rollout_status`, `check_rollout`
- 5 rollout levels: `disabled`, `internal_only`, `pilot_readonly`, `pilot_with_approval`, `limited_automation`
- 5 capabilities gated: `run_query`, `team_workflows`, `provider_selection`, `approval_linked_execution`, `auto_remediation`
- GET `/rollout/profile` — query current rollout profile
- GET `/rollout/status` — full rollout status with per-capability gating state
- POST `/rollout/reload` — reload profile from `rollout_profile.json`
- Rollout gating integrated in `/run`, `/provider/select`, `/auto-remediation/evaluate`
- **Alert-triggered auto-remediation also gated** — `alert.py` `_trigger_auto_remediation` checks rollout before firing
- Blocked operations return 403 with `error: "rollout_gated"` and clear gating message
- Audit log records all rollout-gated denials (including alert flow)
- Config section in `config.example.json` under `rollout_profile`
- 32 unit tests + 5 smoke checks + 16 verify setup checks
- Commits: `21bb1da` (feature) + `0de22e2` (findings fix)

### P14-2 Test Data Pack (completed)

- 6 core test cases covering all main system capabilities
- 1. ORD-2001 正常單 → delivery-risk-analysis (low risk baseline)
- 2. ORD-2002 交期風險單 → delivery-risk-analysis, expedite-options
- 3. ORD-2003 缺料單 → material-shortage-recovery, supplier-followup-draft
- 4. ORD-2004 排程衝突單 → schedule-conflict-check, capacity-rebalance
- 5. ORD-2005 高風險需審批 → guardrails, approval queue (requires API ops)
- 6. ORD-2006 incident closure → alerts, auto-remediation, incident report, closure (requires API ops)
- New data across orders/work_orders/materials/machines/operators/schedule/quotes
- TEST_DATA.md: test case documentation with recommended API test paths
- Commit: `1306e42`

### P14-3 Dashboard Localization and Operator UX Refresh (completed)

- Full Traditional Chinese localization across all UI elements
- Navigation reordering: 查詢工作台 (default) → 運營管理 → 時間軸 → 歷史記錄 → 技能與團隊 → 統計資料
- Card titles: 系統狀態, 健康診斷, 降級狀態, 資料目錄, 快速操作, 待審批項目, 唯讀供應商診斷, 資料來源切換
- Quick action buttons: 重設警報, 重載設定, 重載政策, 健康檢查
- Provider modes: 本機, 遠端, 自動
- All descriptions, button labels, empty states, filter options in zh-Hant
- Added query quick examples for test data cases (ORD-2001~2004)
- All tests updated to match Chinese labels
- Commit: `ddcb486`

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
| P12 | ~~Automation policy controls~~ | ~~Config-driven severity tiers for auto-remediation~~ | ~~severity levels, risk-based cooldowns, tests~~ | ~~P11-3~~ | ~~Codex~~ |
| P12 | ~~Rollback & audit visibility~~ | ~~Track auto-actions with rollback capability~~ | ~~rollback log, audit trail enhancement, tests~~ | ~~P12-1, P11-1~~ | ~~Codex~~ |

## P13 Operator Pilot Readiness

Goal: Make limited automation understandable, reviewable, and operationally safe enough for an operator-facing pilot.

### Roadmap

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P13 | ~~Approval replay preview visibility~~ | ~~Show operators exactly what approve-and-retry will replay before they execute it~~ | ~~Sanitized request preview, approval detail endpoint, dashboard risk labels, tests~~ | ~~P12 complete~~ | ~~Codex~~ |
| P13 | ~~Automation execution receipts~~ | ~~Provide a single operator-facing record for approval retries and auto-remediation outcomes~~ | ~~execution_receipts.py, /automation/receipts, /automation/receipts/reset, integration with auto_remediation and approve-and-retry, tests~~ | ~~P13-1~~ | ~~Codex~~ |
|| P13 | ~~Incident closure workflow~~ | ~~Make incident follow-up and resolution status explicitly operable~~ | ~~Resolution notes/status transitions, incident linkage, tests~~ | ~~P11-2, P13-2~~ | ~~Codex~~ |
|| P13 | ~~Pilot readiness checklist~~ | ~~Codify human pilot prerequisites across safety, observability, and workflow completion~~ | ~~pilot_checklist.py, /pilot/checklist endpoint, aggregated status surface, tests~~ | ~~P13-1 to P13-3~~ | ~~Codex~~ |

## P15 Decision Governance & Explainability Layer

Goal: Unify scattered guardrail/rollout logic into a standardized Decision Contract with operator-facing explainability.

### P15-1 Unified Decision Schema (pending)
### P15-2 MASL-style Guardrail Refactor (pending)

### P15-3 Explainable API Responses (completed)

- `guardrails.py`: Returns `reason`, `decision_state`, `next_action`, `requires_approval`
- `rollout_profile.py`: Same explainability fields for all rollout-gated denials
- `server.py`: `_send_error_response` supports `explainability` param, merged into response body
- Commit: `af66ceccb79126be899329becda6a118efd8fc8b`

### P15-4 Dashboard Decision Inspector (completed)

- `static/dashboard.html`: New "決策說明" card rendered when API responses contain `decision_state`
- `renderDecisionInspector()` parses explainability fields and displays:
  - `目前狀態` → 已被規則阻擋 / 需要審批 / 功能尚未開放 (color-coded)
  - `原因` → from `data.reason`
  - `下一步` → from `data.next_action`
  - `審批` → 需要審批 / 不需審批 (from `data.requires_approval`)
- `doAction()` detects `decision_state` + `reason` presence, renders structured card instead of inline text
- 10 new unit tests in `tests/test_dashboard_actions.py` (`DecisionInspectorHTMLTest`)
- Zero breaking changes — backward compatible with existing API responses
- Commit: `8732e53` `feat(P15-4): add dashboard decision inspector for explainability`

### P15 Completion Assessment (2026-05-14)

- **P15-1**: 可延後 — Decision schema 已透過 P15-3/4 API 回應格式事實存在
- **P15-2**: 可延後 — Guardrail 架構已是純函數 + handler 分層，MASL 模式已滿足
- **P15 判定**: 可視為完成，P16 可開始
- 完整評估：`docs/P15_COMPLETION_ASSESSMENT.md`

## P16 Scene-Based Operator Visibility

Goal: Replace engineering-card UI with an intuitive factory-floor scene view for operator monitoring.

### P16-1 Read-Only Agent Team Scene View (completed)

- `static/dashboard.html`: New "場景視圖" nav + view with agent grid layout
- 10 agent nodes across 5 zones (主控區, 風險評估區, 生產計畫區, 商務區, 通訊協調區)
- Status badges: 待機, 執行中, 待審批, 已阻擋 — derived from /approvals, /history, /guardrails
- Click-to-inspect detail panel with skill ID, status, related approvals, recent history
- Scene-floor grid overlay + pulse animations for active agents
- 20 unit tests in `tests/test_scene_view.py` (P16-1 baseline)
- Read-only: no mutation operations from scene view
- Commit: `d009d24`

### P16-2 Scene Detail & Event Projection (completed)

- `static/dashboard.html` enhanced scene view with multi-source event projection
- Expanded data sources: `/incident/report`, `/automation/receipts`, `/timeline`, `/alerts`
- Per-agent event badges: approval_required, blocked, incident, receipt, alert
- Scene legend (狀態與事件說明) showing all status colors and event marker meanings
- Detail panel enhanced with:
  - Explainability section (reason + next_action, derived from approvals/errors/guardrails)
  - Approval details with risk level and timestamp
  - Automation receipts display
  - Incident report summary when relevant
  - Related timeline events
- Conservative approach: "目前無阻擋說明", "目前無待審批" when no data
- 12 additional unit tests in `tests/test_scene_view.py` (P16-2 enhancements)
- Total scene tests: 32/32
- Zero new API endpoints — all data from existing endpoints
### P16-3 Visual Asset / Scene Styling Upgrade (completed)

- Complete visual overhaul of scene view to look more like a "factory floor" scene
- New `.zone-card` components replace basic zone labels — room/workspace panels
  with colored left borders and gradient backgrounds per zone type
- Scene header with title, description, and Read-Only badge
- Agent nodes upgraded: 3D-ish gradient cards, larger rounded-square icons,
  improved hover/selected states with cubic-bezier transitions
- Status badges redesigned with colored borders for better visibility
- Scene legend enhanced with section headers and improved dot styling
- Zone descriptions added (e.g., "排程、產能與物料", "報價與商務分析")
- Detail panel upgraded: gradient background, larger rounded-square icon,
  refined section dividers
- No new external assets — all improvements via CSS (gradients, box-shadows, borders)
- No changes to data logic, event projection, or read-only behavior
- Tests updated: `.zone-card` / `.zone-card-header` replace old `.scene-zone-label`
- Commit: `63f9b18`

### P16 Completion Assessment (2026-05-14)

- **P16 判定**: 可視為完成，P17 可開始
- 完整評估：`docs/P16_COMPLETION_ASSESSMENT.md`

## Start Here

When a new Codex / AI session starts, do this first:

1. Pull latest `main`
2. Read this file
3. Check `skills/registry.py`, `run_agent.py`, `integrations/asana_client.py`
4. Start with the next unfinished roadmap item, currently P13 phase is complete — define next phase or expand P13 scope

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

## P15 Candidate — Decision Governance & Explainability (Research Phase)

> **Status**: Research complete. Not yet implemented.
> **Reference**: `afu-brain` MASL (Model-Agnostic Safety Layer) pattern.
> **Full Analysis**: See `docs/AFU_BRAIN_RESEARCH.md`

### Candidate Direction

**Goal**: Unify scattered `risk`, `approval`, `guardrail`, and `rollout` logic into an explicit **Decision Contract** layer, providing full operator explainability for all blocking/approval decisions.

### Recommended Sub-tasks (Candidates)

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P15 (Candidate) | Unified Decision Schema | Define `Decision` data structure for all guarded ops | `Decision` type, `intent` -> `risk` -> `decision` mapping | P14 complete | Codex |
| P15 (Candidate) | MASL-style Guardrail Refactor | Decouple guardrail evaluation from HTTP handlers | Pure function `evaluate_decision()`, policy file | Decision schema | Codex |
| P15 (Candidate) | Explainable API Responses | Return `reason` + `suggestion` on all 403/409 blocks | API response enhancement, dashboard parsing | Guardrail refactor | Codex |
| P15 (Candidate) | Dashboard Decision Inspector | Visual panel showing why an action is blocked/requires approval | UI card, `decision_trace` rendering | Explainable API | Codex |

### First Minimal Viable Item
**P15-3: Explainable API Responses** — ✅ **COMPLETED**. Zero-breaking-change enhancement to return structured `reason`, `next_action`, `decision_state`, and `requires_approval` on all guardrail/rollout denials. Dashboard minimally wired to display these fields.

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
P13-4 complete. P13 phase fully delivered (P13-1 through P13-4). Define next roadmap phase or expand P13 scope.

Requirements:
- Reuse the existing routing, schema, team execution, API, provider, policy, deployment, and observability layers instead of replacing them
- Do not re-open completed P4 work unless a new blocking issue is found
- Keep the unified schema, history, dashboard, CLI output, and Asana formatting behavior compatible
- Prefer minimal, incremental changes
- Add tests
- Update README and NEXT_STEPS.md if needed
- Run tests and report results
```
