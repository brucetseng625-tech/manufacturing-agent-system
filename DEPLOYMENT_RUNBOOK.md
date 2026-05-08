# Deployment Runbook

## System Overview

Manufacturing AI Agent System — decision support for order delivery risk, scheduling, procurement, and supplier communication.

- **Zero external dependencies**: Python 3.11+ stdlib only
- **Single binary mode**: `server.py` serves API + dashboard
- **CLI mode**: `run_agent.py` for one-off queries
- **Data layer**: Pluggable provider (local JSON/CSV → live ERP/MCP → auto failover)
- **Policy layer**: Configurable decision thresholds via `policies/active.json`
- **Audit**: JSONL logs in `logs/runs.jsonl`

## Quick Start

### 1. Clone and Verify

```bash
git clone https://github.com/brucetseng625-tech/manufacturing-agent-system.git
cd manufacturing-agent-system
python3 -B -m unittest discover -s tests
```

Expected: All tests pass (280+ tests).

### 2. Verify Environment

```bash
python3 -c "import sys; print(f'Python {sys.version}')"
# Must be 3.11+

python3 run_agent.py --policy
# Should show default policy

python3 server.py --port 8000 &
sleep 1
curl http://localhost:8000/health
# Should return {"status": "ok"}
kill %1
```

### 3. Start the Server

```bash
# Basic mode (no Asana)
python3 server.py --port 8000

# With Asana integration
export ASANA_ACCESS_TOKEN="your-pat"
python3 server.py --port 8000
```

### 4. Open Dashboard

```bash
open http://localhost:8000
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ASANA_ACCESS_TOKEN` | Optional | Asana PAT for posting task comments |
| `PORT` | Optional | Default port for server (default: 8000) |
| `AGENT_LOG_DIR` | Optional | Custom audit log directory (default: `logs/` in CWD) |

### Policy Configuration

Place a JSON file at `policies/active.json` to override decision thresholds. See README.md for details.

### Data Source Configuration

| Mode | CLI Flag | API Field | Description |
|------|----------|-----------|-------------|
| `local` | `--data-source local` | `"data_source": "local"` | JSON/CSV files (default) |
| `live` | `--data-source live` | `"data_source": "live"` | MCP/ERP connector |
| `auto` | `--data-source auto` | `"data_source": "auto"` | Live with local fallback |

### Data Directory

Default: `mock_data/` (JSON) or `data/` (CSV)
Override: `--data-dir /path/to/data` (CLI) or `"data_dir": "/path"` (API)

## Health Checks

### Server Health

```bash
curl http://localhost:8000/health
```

Expected: `{"status": "ok"}`

### Smoke Test

```bash
python3 -m scripts.smoke_test
```

Verifies:
- All API endpoints respond correctly
- CLI executes queries without error
- Dashboard serves HTML
- Policy endpoint returns config
- Skills list is complete
- Team workflows produce results

### Audit Log Verification

```bash
# Check logs exist and are valid JSONL
python3 -c "
import json, os, glob
log_files = glob.glob('logs/runs.jsonl')
if log_files:
    with open(log_files[0]) as f:
        for line in f:
            json.loads(line)  # Validate JSON
    print('Audit log OK')
else:
    print('No audit logs yet')
"
```

## Rollback

### Code Rollback

```bash
# Revert to previous commit
git log --oneline -5  # Find target commit
git checkout <commit-hash>
python3 -B -m unittest discover -s tests  # Verify tests pass
```

### Policy Rollback

```bash
# Remove or rename active.json to restore defaults
mv policies/active.json policies/active.json.bak
python3 run_agent.py --policy  # Verify defaults restored
```

### Data Rollback

```bash
# Restore data from backup
git checkout HEAD -- mock_data/
# Or restore from CSV backup
cp data/orders.csv.bak data/orders.csv
```

## Monitoring

### Key Metrics to Track

- API response times (should be < 500ms for standard queries)
- Error rate (`/run` endpoint 4xx/5xx responses)
- Audit log volume (queries per day)
- Asana post success rate

### Log Analysis

```bash
# Count recent runs
wc -l logs/runs.jsonl

# Filter errors
grep '"status": "error"' logs/runs.jsonl | wc -l

# Most used skills
python3 -c "
import json
from collections import Counter
skills = []
with open('logs/runs.jsonl') as f:
    for line in f:
        r = json.loads(line)
        skills.append(r.get('skill', 'unknown'))
for skill, count in Counter(skills).most_common():
    print(f'{skill}: {count}')
"
```

## Troubleshooting

### Server won't start

- Check port availability: `lsof -i :8000`
- Check Python version: `python3 --version` (must be 3.11+)
- Check file permissions: `ls -la server.py`

### Tests fail

- Run with verbose output: `python3 -B -m unittest discover -s tests -v`
- Check for file changes: `git status`
- Verify mock data: `ls mock_data/`

### Asana posts fail

- Check token: `echo $ASANA_ACCESS_TOKEN` (should be set, not empty)
- Check network connectivity
- Check task GID exists in Asana

### Policy changes not taking effect

- Verify JSON syntax: `python3 -m json.tool policies/active.json`
- Check file location: `policies/active.json` relative to repo root
- Verify via CLI: `python3 run_agent.py --policy`

## Staging / Pilot Checklist

Before rolling out to production:

- [ ] All 280+ tests pass
- [ ] Server starts without errors
- [ ] `/health` returns 200
- [ ] Smoke test passes (`python3 -m scripts.smoke_test`)
- [ ] Policy file validated (`python3 -m json.tool policies/active.json`)
- [ ] Data directory contains required files
- [ ] Audit log directory writable
- [ ] Asana token tested (if using Asana integration)
- [ ] Dashboard accessible in browser
- [ ] Team workflows produce correct results
- [ ] Error handling tested (invalid query, missing order, etc.)
- [ ] Rollback plan documented and tested
