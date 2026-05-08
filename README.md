
# Manufacturing AI Agent System

Enterprise workflow layer for manufacturing decision support.

## MVP Scope

- **Goal**: Answer "Can this urgent order ship on time?"
- **Input**: Natural Language Query via CLI
- **Output**: Structured Decision Report

## Run

```bash
# Start the server (includes web dashboard + API)
python3 server.py --port 8000

# Open dashboard in browser
open http://localhost:8000
```

```bash
python3 run_agent.py "這張急單 ORD-1001 能不能準時出？"
```

Run with CSV sample data:

```bash
python3 run_agent.py --data-dir data "這張急單 ORD-CSV-001 能不能準時出？"
```

Generate a customer-facing sales reply draft:

```bash
python3 run_agent.py "請幫我寫 ORD-1001 的客戶回覆草稿"
```

## Test

```bash
python3 -B -m unittest discover -s tests
```

## Current Prototype

The current workflows route queries to:

- `delivery-risk-analysis`
- `schedule-conflict-check`
- `quote-comparison-summary`
- `sales-response-draft`
- `internal-action-summary`
- `expedite-options`
- `material-shortage-recovery`
- `capacity-rebalance`
- `supplier-followup-draft`

The current team workflows include:

- `team:comprehensive-analysis`
- `team:risk-response`
- `team:recovery-planning`

It reads mock data from:

- `mock_data/orders.json`
- `mock_data/work_orders.json`
- `mock_data/materials.json`
- `mock_data/machines.json`
- `mock_data/operators.json`
- `mock_data/schedule.json`

It can also read CSV exports from:

- `data/orders.csv`
- `data/work_orders.csv`
- `data/materials.csv`
- `data/machines.csv`
- `data/operators.csv`
- `data/schedule.csv`

Before running an agent workflow, the CLI validates required fields, empty values, numeric fields, and date/datetime formats. If validation fails, the run stops with clear errors.

## Data Model

The system reads structured data from JSON or CSV files. Below are the supported datasets and their key fields.

### Core Datasets

| Dataset | Key Fields | Purpose |
|---------|-----------|---------|
| **orders** | `order_id`, `customer`, `product`, `quantity`, `due_date`, `priority` | Order master data |
| | `customer_tier` (VIP/Standard/Budget) | Customer priority tier |
| | `penalty_per_day` (float) | Late delivery penalty cost per day |
| | `expedite_option` (none/overtime/extra_shift) | Available expedite method |
| | `expedite_cost` (float) | Estimated cost to expedite |
| **work_orders** | `wo_id`, `order_id`, `status`, `machine_id`, `progress_percent`, `estimated_completion` | Production work orders |
| **materials** | `order_id`, `material`, `required_qty`, `available_qty`, `status` | Material availability |
| | `safety_stock` (int) | Minimum safety stock level |
| | `supplier_lead_time_days` (int) | Days to reorder material |
| | `supplier_reliability` (float 0–1) | Supplier on-time delivery rate |
| | `unit_cost` (float) | Per-unit material cost |
| **machines** | `machine_id`, `status`, `load_percent`, `next_maintenance` | Machine status |
| | `backup_available` (bool) | Is a backup machine available? |
| | `max_capacity_percent` (int) | Maximum theoretical capacity |
| | `overtime_available` (bool) | Can run overtime? |
| **operators** | `operator_id`, `skill`, `shift`, `status` | Workforce coverage |
| **schedule** | `order_id`, `machine_id`, `start`, `end` | Production schedule |
| **quotes** | `quote_id`, `material`, `supplier`, `unit_price`, `lead_time_days`, `moq`, `quality_rating`, `risk_level`, `valid_until` | Supplier quotes |

### Decision Integration

New fields directly affect `delivery-risk-analysis` decisions:
- **Safety stock breaches** add blockers when `available_qty <= safety_stock`.
- **Supplier lead time vs. due date** determines if reordering is feasible.
- **Supplier reliability** adjusts effective lead time (lower reliability = longer effective lead).
- **Machine backup availability** prevents "machine down" from becoming a blocker.
- **Customer tier + penalty** determines escalation path (VIP + high penalty → immediate VP escalation).
- **Expedite options** are recommended in next_action with cost estimates.

### Quote Comparison Scoring

The `quote-comparison-summary` skill uses a **weighted scoring system** (0–100) to rank suppliers:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| Price | 30% | Cheapest supplier scores 100, most expensive scores 0 |
| Supplier Reliability | 25% | `supplier_reliability` field (0–1), fallback to risk_level if missing |
| Quality Rating | 20% | `quality_rating` normalized from 0–5 scale |
| Lead Time | 15% | Fastest scores 100, slowest scores 0 |
| Risk Level | 10% | low=100, medium=50, high=0 |

The output includes:
- **`supplier_scores`**: Per-supplier total score and 5-criteria breakdown.
- **`tradeoffs`**: Notable tradeoffs (e.g., "Supplier B is cheaper but less reliable").
- **Confidence**: Based on score margin between 1st and 2nd place (≥10 = high, ≥5 = medium, <5 = low).

### Extending the Schema

Add new fields to `data_validator.py` SCHEMAS dict. Optional fields should be added to the `types` section (not `required`) to maintain backward compatibility with existing data files.

## Config Management Layer

Application defaults are now centralized in `config.py`, with support for JSON config files plus environment variable overrides.

### Inspecting Active Config

**CLI:**
```bash
python3 run_agent.py --show-config
```

**API:**
```bash
# Sanitized config (default)
curl http://localhost:8000/config

# Raw config including internal metadata
curl "http://localhost:8000/config?raw=true"
```

### Reloading Config

**API:**
```bash
# Reload default config.json
curl -X POST http://localhost:8000/config/reload

# Reload from custom path
curl -X POST http://localhost:8000/config/reload \
  -H "Content-Type: application/json" \
  -d '{"config_path": "/path/to/config.json"}'
```

### Environment Overrides

The following environment variables are supported:

- `MAS_SERVER_PORT`
- `MAS_DEFAULT_DATA_DIR`
- `MAS_DEFAULT_DATA_SOURCE`
- `MAS_HISTORY_LAST`
- `MAS_METRICS_WINDOW_HOURS`
- `MAS_POLICY_CONFIG_PATH`
- `MAS_LOG_DIR`
- `MAS_API_TOKEN`
- `MAS_DEFAULT_ASANA_TASK`

See `config.example.json` for a full file-based configuration example.

## Configurable Policy Layer

All decision thresholds, routing weights, and escalation rules are now centralized in `skills/policy.py` and can be overridden via a JSON config file.

### Default Behavior

Without any config file, the system uses built-in defaults that exactly match the previous hardcoded behavior.

### Config File

Place a JSON file at `policies/active.json` to override policy values. Only specify the values you want to change — all others fall back to defaults.

**Example `policies/active.json`:**
```json
{
  "routing": {
    "exact_keyword_weight": 10
  },
  "delivery_risk": {
    "at_risk_blocker_max": 3,
    "vip_penalty_threshold": 5000
  },
  "quote_scoring": {
    "price_weight": 0.40,
    "reliability_weight": 0.30,
    "quality_weight": 0.15,
    "lead_time_weight": 0.10,
    "risk_weight": 0.05
  }
}
```

### Inspecting Active Policy

**CLI:**
```bash
python3 run_agent.py --policy
```

**API:**
```bash
curl http://localhost:8000/policy
```

### Policy Hot-Reload

Adjust thresholds without restarting the server. Reloads `policies/active.json` and immediately applies new values to all active threads.

**CLI:**
```bash
python3 run_agent.py --reload-policy
```

**API:**
```bash
# Reload from default path (policies/active.json)
curl -X POST http://localhost:8000/policy/reload

# Reload from custom path
curl -X POST http://localhost:8000/policy/reload \
  -H "Content-Type: application/json" \
  -d '{"config_path": "/path/to/custom.json"}'
```

Response includes `success`, `source`, `reload_count`, and `reloaded_at`. If the config file is missing or invalid, the system falls back to built-in defaults without crashing.

### Policy Sections

| Section | Controls |
|---------|----------|
| `routing` | Keyword matching weights for skill/team routing |
| `delivery_risk` | Blocker thresholds, VIP penalty escalation |
| `quote_scoring` | Supplier scoring weights (price, reliability, quality, lead time, risk) |
| `option_ranking` | Feasibility scores and recommendation bonuses |
| `shortage_recovery` | Reliability thresholds, partial production criteria |
| `capacity_rebalance` | Capacity pressure threshold, penalty criteria |
| `supplier_followup` | Urgency level priorities |
| `defaults` | Reliability defaults, emergency lead reduction |

## Observability and Traceability

Every run is assigned a unique **Run ID** (`run-YYYYMMDD-XXXXXX`) at the orchestrator entry point. This ID flows through the entire execution pipeline:

### Run ID Usage

| Layer | How Run ID Appears |
|-------|-------------------|
| **CLI Output** | Printed as `Run ID: run-20260508-abc123` after data validation |
| **API Response** | Included in `/run` response body as `run_id` field |
| **Audit Log** | Every `logs/runs.jsonl` record includes `run_id` |
| **Asana Comments** | Report headers include `Run ID: \`run-...\`` for trace linking |
| **Structured Logs** | All `logs/events.jsonl` events are tagged with `run_id` |

### Querying by Run ID

**CLI:**
```bash
python3 run_agent.py --history --run-id run-20260508-abc123
```

**API:**
```bash
curl "http://localhost:8000/history?run_id=run-20260508-abc123"
```

### Structured Event Log

The system writes lifecycle events to `logs/events.jsonl` covering:
- `request` — incoming query (CLI or HTTP)
- `routing` — skill/team matching decision
- `skill_start` / `skill_end` — individual skill execution
- `team_start` / `team_end` — team workflow execution
- `error` — any error with type, message, and context
- `asana_post` — Asana comment post attempt and result
- `complete` — final run status with duration

Each event includes timestamp, event type, and associated run_id for correlation.

## Team Workflow Execution

Team workflows execute their steps **in parallel** using `ThreadPoolExecutor` for maximum throughput:

- **Parallel Execution**: All steps in a team run concurrently (e.g., `comprehensive-analysis` runs risk, sales, and internal analysis simultaneously).
- **Integrated Planning Pack**: `recovery-planning` bundles `material-shortage-recovery`, `expedite-options`, `capacity-rebalance`, and `supplier-followup-draft` for one coordinated recovery/planning view.
- **Deterministic Ordering**: Despite parallel execution, `results` keys, trace entries, and CLI output always follow the original step definition order.
- **Partial Failure**: If some steps fail, the team returns `partial_success: true` with successful results intact. If all steps fail, it returns `team_error`.
- **Summary**: Each team result includes `summary.parallel: true`, `success_count`, and `failed_count`.
- **Future Dependencies**: The current design assumes steps are independent. Future versions may support step dependencies for sequential sub-chains.

Each CLI or HTTP run writes a JSONL audit record to `logs/runs.jsonl` under the current working directory. Set `AGENT_LOG_DIR` to write logs elsewhere.

The report includes:

- delivery decision
- confidence
- evidence
- blockers
- recommendation
- customer reply draft
- trace

## Asana Integration

Post agent results to Asana task comments:

```bash
export ASANA_ACCESS_TOKEN="your-personal-access-token"
python3 run_agent.py --asana-task 123456789 "ORD-1001 能不能準時出？"
```

- Results are posted as comments to the specified task GID.
- Both success and failure results are reported.
- Token must be set via environment variable (never commit tokens).

## Web API / Local Service

Run as a local HTTP service for external integration:

```bash
python3 server.py --port 8000
```

To allow `/run` to post results to Asana, set `ASANA_ACCESS_TOKEN` before starting the server:

```bash
export ASANA_ACCESS_TOKEN="your-personal-access-token"
python3 server.py --port 8000
```

### API Authentication

All mutation endpoints (`POST /run`, `POST /batch`, `POST /config/reload`, `POST /policy/reload`) require authentication when an API token is configured. Read-only endpoints (`GET /health`, `GET /config`, `GET /metrics`, etc.) remain accessible without a token.

**Dev mode**: If no token is configured (`security.api_token` is empty or `null`), all requests are allowed.

**Configure a token** via `config.json` or environment:

```json
{
  "security": {
    "api_token": "your-secret-token"
  }
}
```

```bash
export MAS_API_TOKEN="your-secret-token"
python3 server.py --port 8000
```

**Authenticate requests** using one of:
- `Authorization: Bearer <token>` header
- `X-API-Token: <token>` header

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token" \
  -d '{"query": "ORD-1001 出貨"}'
```

Unauthorized requests return `401` with:
```json
{"status": "error", "error_type": "unauthorized", "message": "Invalid or missing API token"}
```

### Endpoints

- **GET /health**
  ```bash
  curl http://localhost:8000/health
  ```
  Response: `{"status": "ok"}`

- **POST /run**
  ```bash
  curl -X POST http://localhost:8000/run     -H "Content-Type: application/json"     -d '{
      "query": "ORD-1001 能不能準時出？",
      "data_dir": "mock_data",
      "asana_task": "123456789"
    }'
  ```
  - **query**: Natural language query.
  - **data_dir**: Path to data directory (optional, defaults to mock_data).
  - **asana_task**: Asana Task GID (optional, posts result to task).

- **GET /skills**
  ```bash
  curl http://localhost:8000/skills
  ```
  Returns all available skills and team workflows with their metadata:
  ```json
  {
    "total": 7,
    "items": [
      {
        "name": "delivery-risk-analysis",
        "intent": "delivery_risk_analysis",
        "type": "skill",
        "requires_order_id": true,
        "keywords": ["準時", "出貨", "delivery", ...],
        "exact_keywords": ["交期風險", "delivery risk"],
        "priority": 2
      },
      {
        "name": "team:comprehensive-analysis",
        "intent": "comprehensive_analysis",
        "type": "team",
        "requires_order_id": true,
        "keywords": ["全面分析", "comprehensive", ...],
        "exact_keywords": ["comprehensive analysis", "完整報告"],
        "priority": 10,
        "steps": [
          {"skill": "delivery-risk-analysis", "alias": "risk"},
          {"skill": "sales-response-draft", "alias": "sales"},
          {"skill": "internal-action-summary", "alias": "internal"}
        ]
      },
      {
        "name": "team:recovery-planning",
        "intent": "recovery_planning",
        "type": "team",
        "requires_order_id": true,
        "keywords": ["恢復整合", "recovery coordination", "..."],
        "exact_keywords": ["recovery planning", "恢復規劃包"],
        "priority": 11,
        "steps": [
          {"skill": "material-shortage-recovery", "alias": "shortage"},
          {"skill": "expedite-options", "alias": "expedite"},
          {"skill": "capacity-rebalance", "alias": "capacity"},
          {"skill": "supplier-followup-draft", "alias": "supplier"}
        ]
      }
    ]
  }
  ```

- **GET /schema**
  ```bash
  curl http://localhost:8000/schema
  ```
  Returns the unified output schema metadata, including:
  - `top_level_shared_fields`: All standard fields every skill returns.
  - `details_usage`: Explanation and per-skill examples of skill-specific fields.
  - `team_workflow_structure`: Structure of team workflow results.

- **GET /history**
  ```bash
  # Last 5 runs
  curl "http://localhost:8000/history?last=5"

  # Filter by status and skill
  curl "http://localhost:8000/history?status=error&skill=delivery-risk-analysis"

  # Filter by channel
  curl "http://localhost:8000/history?channel=cli&last=20"
  ```
  - **last**: Number of recent records (default: 10).
  - **status**: `success` or `error`.
  - **skill**: Partial match on skill name (e.g., `team:` for all teams).
  - **intent**: Exact match on intent string.
  - **channel**: `cli` or `http`.

  Invalid parameters return HTTP 400 with an error description.

- **GET /metrics**
  ```bash
  # Default 24-hour window
  curl http://localhost:8000/metrics

  # Custom window (e.g., 48 hours)
  curl "http://localhost:8000/metrics?window=48"
  ```
  - **window**: Time window in hours for recent metrics (default: 24).

  Response includes:
  ```json
  {
    "total_runs": 42,
    "success_count": 38,
    "error_count": 4,
    "success_rate": 90.5,
    "skill_distribution": {"delivery-risk-analysis": 15, ...},
    "channel_distribution": {"cli": 20, "http": 22},
    "recent_runs": 12,
    "recent_success_rate": 91.7,
    "last_run_timestamp": "2026-05-08T10:00:00+00:00"
  }
  ```

  - **data_source**: `local`, `live`, or `auto`.

- **GET /config**
  ```bash
  curl http://localhost:8000/config
  curl "http://localhost:8000/config?raw=true"
  ```
  Returns centralized runtime configuration and reload metadata.

- **POST /config/reload**
  ```bash
  curl -X POST http://localhost:8000/config/reload
  ```
  Reloads `config.json` (or a custom path) without restarting the server.

- **GET /data/status**
  ```bash
  # Default data directory (mock_data)
  curl http://localhost:8000/data/status

  # Custom data directory
  curl "http://localhost:8000/data/status?data_dir=/path/to/data"
  ```
  - **data_dir**: Path to data directory (optional, defaults to mock_data).

  Returns data directory metadata:
  ```json
  {
    "data_dir": "/path/to/mock_data",
    "file_count": 6,
    "files": [
      {"name": "orders.json", "path": "...", "mtime": "2026-05-08T..."},
      ...
    ],
    "last_modified": "2026-05-08T...",
    "scanned_at": "2026-05-08T...",
    "error": null
  }
  ```

  Use this to detect when data files have been added, modified, or removed without restarting the server.

- **GET /provider/status**
  ```bash
  # Default data directory
  curl http://localhost:8000/provider/status

  # Custom data directory
  curl "http://localhost:8000/provider/status?data_dir=/path/to/data"
  ```
  Returns active provider metadata including capabilities, readiness state, and sub-provider details (for auto mode):
  ```json
  {
    "name": "local",
    "capabilities": ["read"],
    "readiness": "ready",
    "available": true
  }
  ```

  **Readiness states:**
  - `ready` — Provider is fully operational
  - `not_configured` — Live provider skeleton, no real implementation connected
  - `degraded` — Live source unavailable, running on local fallback
  - `disabled` — Provider cannot serve data
  - `circuit_open` — Circuit breaker tripped, live source temporarily blocked

  **Auto mode** additionally includes `circuit_breaker`, `live_provider`, and `fallback_provider` details.

- **GET /provider/health**
  ```bash
  curl http://localhost:8000/provider/health
  curl "http://localhost:8000/provider/health?data_dir=/path/to/data"
  ```
  Returns provider health diagnostics:
  ```json
  {
    "supported": true,
    "status": "ok",
    "details": {
      "data_dir": "/path/to/mock_data",
      "exists": true,
      "readable": true
    }
  }
  ```

  **Health states:**
  - `ok` — Provider is healthy and operational
  - `unreachable` — Data source or directory not found
  - `not_configured` — Live provider skeleton (no real implementation connected)
  - `degraded` — Live source down, running on local fallback
  - `circuit_open` — Circuit breaker tripped, live source temporarily blocked
  - `unhealthy` — Both live and fallback sources have issues

- **POST /batch**
  ```bash
  curl -X POST http://localhost:8000/batch \
    -H "Content-Type: application/json" \
    -d '{
      "queries": ["ORD-1001 能不能準時出？", "ORD-1002 檢查排程衝突"],
      "data_dir": "mock_data"
    }'
  ```
  - **queries**: List of natural language queries.
  - **data_dir**: Path to data directory (optional).
  - **data_source**: Data source mode (optional).

  Returns batch summary and individual results:
  ```json
  {
    "total": 2,
    "success_count": 2,
    "error_count": 0,
    "results": [
      {"index": 0, "query": "...", "result": {"status": "success", ...}},
      {"index": 1, "query": "...", "result": {"status": "success", ...}}
    ]
  }
  ```

### Response Format

```json
{
  "status": "success",
  "intent": "delivery_risk_analysis",
  "order_ids": ["ORD-1001"],
  "data": { ... },
  "asana_task": "123456789",
  "asana_posted": true
}
```

- `asana_posted`: `true` (success), `false` (post failed), or `null` (no asana_task provided).

## Audit Log

Every CLI or HTTP execution is automatically recorded in `logs/runs.jsonl` for tracking and debugging.

### Log Format
One JSON object per line (JSONL):
```json
{
  "timestamp": "2026-05-07T14:30:00.123456+00:00",
  "channel": "cli",
  "query": "ORD-1001 出貨",
  "data_dir": "mock_data",
  "status": "success",
  "intent": "delivery_risk_analysis",
  "order_ids": ["ORD-1001"],
  "skill": "delivery-risk-analysis",
  "asana_task": "12345",
  "asana_posted": true,
  "error_type": null,
  "trace": ["loaded orders", "checked risk"]
}
```

- `channel`: `cli` or `http`.
- `trace`: Execution steps from the skill (only for success).
- `error_type`: Validation or system error type (only for errors).
- Logs are excluded from Git via `.gitignore`.

## Run History

Query and filter past execution records from the audit log:

```bash
# Show last 5 runs
python3 run_agent.py --history --last 5

# Show only error runs
python3 run_agent.py --history --status error

# Show runs for a specific skill
python3 run_agent.py --history --skill delivery-risk-analysis

# Show only CLI runs
python3 run_agent.py --history --channel cli --last 10
```

### API Endpoint

When the server is running, query history via:

```bash
# Last 5 runs
curl "http://localhost:8000/history?last=5"

# Filter by status and skill
curl "http://localhost:8000/history?status=error&skill=delivery-risk-analysis"

# Filter by channel
curl "http://localhost:8000/history?channel=cli&last=20"
```

Response format:
```json
{
  "total": 3,
  "filters": {"last": 10, "status": "error", "skill": null, "channel": null},
  "runs": [ ... ]
}
```

### Filters

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--last`  | int    | Number of recent records (default: 10) |
| `--status`| `success`, `error` | Filter by execution status |
| `--skill` | string | Partial match on skill name (e.g., `team:` for all team workflows) |
| `--channel`| `cli`, `http` | Filter by execution channel |

## Data Source Architecture

The system uses a pluggable **data provider** abstraction so skills can read data from local files, live ERP/MCP sources, or a hybrid auto-failover mode — without any changes to skill logic.

### Provider Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `local` (default) | Reads from JSON/CSV files on disk | Development, demo, offline |
| `live` | Connects to a live data source (MCP, REST API, database) | Production ERP integration |
| `auto` | Tries live source first; falls back to local on failure | Gradual migration, resilience |

### Architecture

```
skills/*.py ──→ data_loader.py ──→ data_source.py (provider layer)
                                     ├── LocalFileProvider  (JSON/CSV)
                                     ├── LiveDataProvider   (MCP/ERP skeleton)
                                     └── AutoFailoverProvider (live + fallback)
```

All skills call `load_json_or_csv(data_dir, filename)` as before. The provider layer intercepts these calls and routes them to the configured source.

### Usage

**CLI:**
```bash
# Default: local files
python3 run_agent.py "ORD-1001 能不能準時出？"

# Explicit local mode
python3 run_agent.py --data-source local "ORD-1001 能不能準時出？"

# Auto mode (live with local fallback)
python3 run_agent.py --data-source auto "ORD-1001 能不能準時出？"
```

**API:**
```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"query": "ORD-1001 準時出貨", "data_source": "local"}'
```

Response includes the active provider:
```json
{"status": "success", "data_source": "local", ...}
```

### Adding a Live Provider

Subclass `LiveDataProvider` and override `load()` and `is_available()`:

```python
from data_source import LiveDataProvider, set_data_source

class MyERPProvider(LiveDataProvider):
    def load(self, data_dir, filename):
        # Call your ERP API / MCP server here
        return fetch_from_erp(filename)

    def is_available(self, data_dir):
        return ping_erp_endpoint()

set_data_source(MyERPProvider())
```

The `AutoFailoverProvider` wraps your live provider with automatic fallback to local files when the live source is unavailable or returns an error.

### Circuit Breaker (Auto Mode)

When using `auto` data source mode, an optional **circuit breaker** prevents repeated calls to a failing live source:

- **Closed**: normal operation, live provider receives all requests
- **Open**: after consecutive failures reach threshold, circuit opens — all requests fail-fast to local fallback without hitting the live source
- **Half-open**: after the recovery timeout, one probe call is allowed. If it succeeds, circuit closes; if it fails, circuit reopens

Configure via `config.json`:

```json
{
  "live_provider": {
    "circuit_breaker": {
      "failure_threshold": 3,
      "recovery_seconds": 60
    }
  }
}
```

Set `failure_threshold` to `0` (default) to disable the circuit breaker and use simple failover.

### Server Access Logging

Enable structured HTTP access logging to track all requests to the server:

```json
{
  "logging": {
    "access_log": true
  }
}
```

Or via environment variable:

```bash
export MAS_ACCESS_LOG=true
```

Access logs are written as JSONLines to `logs/access.log`:

```json
{"timestamp": "2026-05-08T14:30:00Z", "method": "GET", "path": "/health", "status_code": 200, "duration_ms": 0.5, "client": "127.0.0.1"}
{"timestamp": "2026-05-08T14:30:01Z", "method": "POST", "path": "/run", "status_code": 200, "duration_ms": 45.2, "client": "127.0.0.1", "run_id": "run-20260508-abc123"}
```

  Use this to detect when data files have been added, modified, or removed without restarting the server.

- **GET /provider/status**
  ```bash
  # Default data directory
  curl http://localhost:8000/provider/status

  # Custom data directory
  curl "http://localhost:8000/provider/status?data_dir=/path/to/data"
  ```
  Returns active provider metadata including capabilities, readiness state, and sub-provider details (for auto mode):
  ```json
  {
    "name": "local",
    "capabilities": ["read"],
    "readiness": "ready",
    "available": true
  }
  ```

  **Readiness states:**
  - `ready` — Provider is fully operational
  - `not_configured` — Live provider skeleton, no real implementation connected
  - `degraded` — Live source unavailable, running on local fallback
  - `disabled` — Provider cannot serve data
  - `circuit_open` — Circuit breaker tripped, live source temporarily blocked

  **Auto mode** additionally includes `circuit_breaker`, `live_provider`, and `fallback_provider` details.

- **GET /provider/health**
  ```bash
  curl http://localhost:8000/provider/health
  curl "http://localhost:8000/provider/health?data_dir=/path/to/data"
  ```
  Returns provider health diagnostics:
  ```json
  {
    "supported": true,
    "status": "ok",
    "details": {
      "data_dir": "/path/to/mock_data",
      "exists": true,
      "readable": true
    }
  }
  ```

  **Health states:**
  - `ok` — Provider is healthy and operational
  - `unreachable` — Data source or directory not found
  - `not_configured` — Live provider skeleton (no real implementation connected)
  - `degraded` — Live source down, running on local fallback
  - `circuit_open` — Circuit breaker tripped, live source temporarily blocked
  - `unhealthy` — Both live and fallback sources have issues

- **GET /system/degradation-status**
  ```bash
  curl http://localhost:8000/system/degradation-status
  curl "http://localhost:8000/system/degradation-status?data_dir=/path/to/data"
  ```
  Returns structured visibility into whether the system is serving in degraded mode, which data path is active, why, and recommended actions:
  ```json
  {
    "is_degraded": true,
    "mode": "auto",
    "active_path": "fallback",
    "reason": "Live provider not configured — using local fallback",
    "live_readiness": "not_configured",
    "fallback_readiness": "ready",
    "circuit_breaker": null,
    "recommendations": [
      "Configure live provider (ERP/MCP endpoint) for full functionality"
    ]
  }
  ```

  **Key fields:**
  - `is_degraded` (bool) — whether the system is serving in a degraded mode
  - `active_path` (str) — which data path is currently serving: `live`, `fallback`, or `none`
  - `reason` (str) — human-readable explanation of why degraded (empty if not degraded)
  - `live_readiness` / `fallback_readiness` — current readiness state of each path
  - `circuit_breaker` — circuit breaker status dict (null if not configured)
  - `recommendations` (list) — actionable suggestions to restore full operation

  **Degradation scenarios detected:**
  - Live provider unavailable → serving from fallback
  - Circuit breaker OPEN → live blocked, fallback serving
  - Live provider readiness degraded/not_configured
  - Rollout controls disabled a path (live or auto)

  All provider modes support `degradation_status()`:
  - `local`: always `is_degraded=false` (this is the intended path)
  - `live`: degraded if live provider not available
  - `auto`: degraded if fallback is active or circuit breaker is open

- **POST /batch**

To add a new skill (e.g., `quote-comparison`, `sales-analysis`), follow these steps:

1. **Create the skill module** in `skills/your_skill.py`:
   ```python
   def handle_your_skill(order_ids, data_dir):
       # Your logic here
       return {"decision": "result", "trace": ["step1", "step2"]}
   ```

2. **Register the skill** in `skills/registry.py`:
   ```python
   from skills.your_skill import handle_your_skill
   
   self.register({
       "name": "quote-comparison",           # Skill identifier
       "intent": "quote_comparison",         # Intent string for response
       "keywords": ["報價", "quote", "price"],# Trigger keywords
       "handler": handle_your_skill,         # Function to call
       "requires_order_id": True,            # Does it need order ID?
       "triggers_on_multi_order": False,     # Auto-route if multiple orders?
       "data_files": ["orders.json"]         # Required data files
   })
   ```

3. **Add tests** in `tests/test_your_skill.py`.

4. **Run all tests** to ensure nothing breaks:
   ```bash
   python3 -B -m unittest discover -s tests
   ```

No changes needed in `orchestrator.py`, `server.py`, or `run_agent.py` — the registry handles routing automatically.

## Internal Action Summary

Use this workflow to generate internal follow-up actions for PM / Ops / Production teams. It analyzes delivery risks and outputs immediate action items, owners, and escalation paths.

```bash
python3 run_agent.py "ORD-1001 行動計畫"
```
