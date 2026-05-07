
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

## Test

```bash
python3 -B -m unittest discover -s tests
```

## Current Prototype

The first workflow routes delivery questions to `delivery-risk-analysis`.

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
python3 server.py
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
