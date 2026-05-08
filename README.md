
# Manufacturing AI Agent System

Enterprise workflow layer for manufacturing decision support.

## MVP Scope

- **Goal**: Answer "Can this urgent order ship on time?"
- **Input**: Natural Language Query via CLI
- **Output**: Structured Decision Report

## Run

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

## How to Add a Skill

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
