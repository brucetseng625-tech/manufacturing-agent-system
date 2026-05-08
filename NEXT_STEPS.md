# Manufacturing Agent System Next Steps

Last updated: 2026-05-08

Current latest completed GitHub commit on `main`:
- `1d56d5a` `feat: enhance quote comparison with weighted supplier scoring`

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

## Start Here

When a new Codex / AI session starts, do this first:

1. Pull latest `main`
2. Read this file
3. Check `skills/registry.py`, `run_agent.py`, `integrations/asana_client.py`
4. Start with the top unfinished item in the Priority 1 section unless the user explicitly reprioritizes

## Roadmap Table

| Priority | Work Item | Goal | Main Deliverables | Depends On | Recommended Owner |
| --- | --- | --- | --- | --- | --- |
| P3 | Parallel team execution | Improve throughput by running independent team steps concurrently | Parallel-safe team executor, ordering rules, tests | Agent Teams MVP and error handling now exist | Codex / systems AI |
| P3 | Web dashboard | Add a visual layer over the existing API and history endpoints | Dashboard screens, API consumption, basic UX | API enhancement and run history support are complete | Frontend AI |
| P3 | MCP / ERP integration | Replace static files with live operational inputs | Connector layer, config, fallback behavior, tests | Current API and data model are stable enough to integrate | Integration AI |
| P3 | New recovery / planning skills | Expand practical manufacturing use cases | `expedite-options`, `material-shortage-recovery`, `capacity-rebalance`, `supplier-followup-draft` | Routing and schema should be stronger first | Feature AI |
| P4 | Configurable rules / policy layer | Move decision rules out of hardcoded logic | Rule config structure, loader, tests | Existing skills stable | Codex |
| P4 | Deployment readiness | Prepare for actual internal use | Runbook, config docs, server mode validation | API and error handling maturity | Codex |
| P4 | Observability and traceability | Make runs easier to audit and support | Run IDs, structured logs, Asana trace linking | Audit log and API available | Codex |

## Suggested Execution Order

| Order | Work Item | Why Now |
| --- | --- | --- |
| 1 | Parallel team execution | Best next step now that team workflows, history, API, and hardening are in place |
| 2 | Web dashboard | High leverage now that structured endpoints exist |
| 3 | MCP / ERP integration | Natural next step once the internal workflow surface is stable |
| 4 | New recovery / planning skills | Safer to add after platform basics are stronger |

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
Implement parallel team execution for independent team workflow steps

Requirements:
- Reuse the existing Agent Teams structure instead of rewriting team routing
- Run independent steps concurrently where ordering is not required, while preserving deterministic output and trace
- Keep CLI, API, formatter, and error-handling behavior stable under parallel execution
- Add tests
- Update README if needed
- Run tests and report results
```
