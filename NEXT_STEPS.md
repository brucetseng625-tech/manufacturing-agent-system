# Manufacturing Agent System Next Steps

Last updated: 2026-05-08

Current latest completed GitHub commit on `main`:
- `75c4346` `feat: add internal-action-summary skill`

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

## Start Here

When a new Codex / AI session starts, do this first:

1. Pull latest `main`
2. Read this file
3. Check `skills/registry.py`, `run_agent.py`, `integrations/asana_client.py`
4. Start with the top unfinished item in the Priority 1 section unless the user explicitly reprioritizes

## Roadmap Table

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P1 | Asana workflow enhancement | Standardize internal reporting back to Asana | Structured comment template with decision, blockers, owner, next action, ETA | `internal-action-summary` now available for reuse | Feature AI |
| P1 | Output schema unification | Make all skills return a predictable shared shape | Shared response fields, formatter updates, regression tests | Existing skills in registry | Codex / integration AI |
| P2 | Query routing improvement | Reduce keyword collisions and improve intent accuracy | Priority-based matching, fallback behavior, routing tests | Current skill registry | Feature AI |
| P2 | Agent Teams implementation | Turn skeleton into usable multi-role workflow | Team definitions, handoff flow, team execution tests | Output schema should be more stable first | Feature AI |
| P2 | Run history query support | Make audit log operationally useful | History reader, compare past runs, optional API endpoint, tests | Audit log already exists | Feature AI |
| P2 | API enhancement | Make external integration easier | `/skills`, `/history`, `/schema` endpoints, tests | Output schema unification recommended | Codex / API AI |
| P3 | Error handling hardening | Improve resilience under bad data or integration issues | Better degraded responses, retry / fallback rules, tests | Existing API and skill outputs | Codex |
| P3 | Data model expansion | Improve decision quality with richer operational inputs | Inventory, supplier lead times, capacity signals, expedite cost fields | Existing core workflows stable | Data / domain AI |
| P3 | New recovery / planning skills | Expand practical manufacturing use cases | `expedite-options`, `material-shortage-recovery`, `capacity-rebalance`, `supplier-followup-draft` | Routing and schema should be stronger first | Feature AI |
| P4 | Configurable rules / policy layer | Move decision rules out of hardcoded logic | Rule config structure, loader, tests | Existing skills stable | Codex |
| P4 | Deployment readiness | Prepare for actual internal use | Runbook, config docs, server mode validation | API and error handling maturity | Codex |
| P4 | Observability and traceability | Make runs easier to audit and support | Run IDs, structured logs, Asana trace linking | Audit log and API available | Codex |

## Suggested Execution Order

| Order | Work Item | Why Now |
| --- | --- | --- |
| 1 | Asana workflow enhancement | Best next step now that external and internal summaries both exist |
| 2 | Output schema unification | Reduces future integration churn |
| 3 | Query routing improvement | Prevents regression as more skills are added |
| 4 | Agent Teams implementation | Builds on more stable interfaces |
| 5 | Run history query support | Makes the system more operationally useful |
| 6 | API enhancement | Easier once outputs and history are more stable |
| 7 | Error handling hardening | Best informed by real workflow growth |
| 8 | Data model expansion | More valuable after workflow scaffolding is stronger |
| 9 | New recovery / planning skills | Safer to add after platform basics are stronger |

## Ready-To-Use Prompt For The Next AI

```text
Please start with /Users/brucetseng/Documents/Codex/2026-05-08/github-repo-https-github-com-brucetseng625/NEXT_STEPS.md

Repo:
https://github.com/brucetseng625-tech/manufacturing-agent-system

First actions:
1. Pull latest main
2. Read NEXT_STEPS.md
3. Confirm latest completed commit
4. Continue from the top Priority 1 item unless the user reprioritizes

Current expected next task:
Implement Asana workflow enhancement for structured internal follow-up reporting

Requirements:
- Reuse existing outputs from `delivery-risk-analysis`, `sales-response-draft`, and `internal-action-summary`
- Extend Asana comment formatting or add a dedicated Asana-ready workflow
- Standardize fields like decision, blockers, owner, next action, ETA
- Add tests
- Update README if needed
- Run tests and report results
```
