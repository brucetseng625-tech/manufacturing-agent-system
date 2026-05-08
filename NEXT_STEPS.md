# Manufacturing Agent System Next Steps

Last updated: 2026-05-08

Current latest completed GitHub commit on `main`:
- `ef55c0d` `feat: add supplier-followup-draft skill for supplier communication`

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

## Start Here

When a new Codex / AI session starts, do this first:

1. Pull latest `main`
2. Read this file
3. Check `skills/registry.py`, `run_agent.py`, `integrations/asana_client.py`
4. Start with the top unfinished item in the Priority 1 section unless the user explicitly reprioritizes

## Roadmap Table

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P4 | Configurable rules / policy layer | Move decision rules out of hardcoded logic | Rule config structure, loader, tests | Existing skills stable | Codex |
| P4 | Deployment readiness | Prepare for actual internal use | Runbook, config docs, server mode validation | API and error handling maturity | Codex |
| P4 | Observability and traceability | Make runs easier to audit and support | Run IDs, structured logs, Asana trace linking | Audit log and API available | Codex |

## Suggested Execution Order

| Order | Work Item | Why Now |
| --- | --- | --- |
| 1 | Configurable rules / policy layer | Best next step now that the major P3 skill surface is complete |
| 2 | Deployment readiness | Natural follow-on once policy boundaries and runtime expectations are clearer |
| 3 | Observability and traceability | High leverage after workflow surface has stabilized |
| 4 | Additional planning refinements | Reserve for future expansion after core platform hardening |

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
Implement Configurable Rules / Policy Layer on top of the current routing, schema, and provider layers

Requirements:
- Reuse the existing routing, schema, team execution, API, and provider layers instead of replacing them
- Move hardcoded decision thresholds and rule selections into a configurable policy structure without changing the current user-facing workflow contracts
- Keep the unified schema, history, dashboard, and Asana formatting behavior compatible
- Add tests
- Update README if needed
- Run tests and report results
```
