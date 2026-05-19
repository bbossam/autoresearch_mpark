# Agents

AutoresearchByMpark is a **control plane**: it plans, validates, runs, and
analyses experiments across separate target projects. It never contains a
target project's code — capsules in `configs/project_capsules/` point at them
by path.

The design follows two principles drawn from existing agentic systems:

- **Intelligence / execution split** (OpenHarness): agents are pure
  decision-makers — they return an `AgentOutcome` and never touch the
  filesystem or spawn processes. The CLI and the watchdog are the only
  execution layer.
- **Hill-climbing loop** (Karpathy autoresearch): a run is a genuine
  improvement only when it beats the recorded best for its metric, tracked in
  `experiments/leaderboard.json`.

## The pipeline

```
(project capsule) ──ResearchAgent──▶ ideas/*.md         [Codex, early stage]
                                         │
                  PlanningAgent ──▶ experiments/contracts/*.yaml
                                         │
                            ValidationAgent  (is the contract sane?)
                                         │
                        ImplementationAgent  (writes target repo — stub in v0)
                                         │
                            ValidationAgent  (is the diff legal?)
                                         │
experiments/logs/*.json ──AnalysisAgent──▶ experiments/reports/*.md + leaderboard
                                         │
                              ReviewAgent ──▶ experiments/reviews/*.md  [Codex]
```

## Roster

| Agent | Module | Role | Writes |
|-------|--------|------|--------|
| ResearchAgent | `agents/researcher.py` | aggressively hypothesise ideas (early stage) | nothing |
| PlanningAgent | `agents/planner.py` | idea + capsule → RunContract | nothing |
| ValidationAgent | `agents/validator.py` | contract & diff gatekeeper | nothing |
| ImplementationAgent | `agents/implementer.py` | apply change to target repo | target repo only (stub in v0) |
| AnalysisAgent | `agents/analyst.py` | judge metrics vs accept rules, render report | nothing |
| ReviewAgent | `agents/reviewer.py` | Codex-review artifacts, triage verdict | nothing |

Only `ImplementerAgent` may carry `may_write=true` in a contract — enforced by
`RunContract` model validation.

## Codex-backed agents (ResearchAgent, ReviewAgent)

Reviewing a huge volume of logs and hypothesising ideas both need judgement, so
these two agents call an LLM via the `codex` CLI ([codex_client.py](src/autoresearch/codex_client.py)).
They stay pure all the same: each builds a prompt and parses the response,
while the actual Codex call is an injected `codex_runner` callable — so they
are fully testable without Codex installed.

- Codex command is configurable via `AUTORESEARCH_CODEX_CMD` (default `codex exec`).
- **Token budgeting** ([tokens.py](src/autoresearch/tokens.py)): before `review` spends a Codex
  call, the prompt is size-checked against `--token-budget`; oversized run logs
  are clipped to `--max-log-tokens` (head + tail) so a giant log never blows
  the context window or wastes a call.

## Watchdog — long, unattended runs

`watchdog.py` runs an experiment command as a real subprocess and writes a
heartbeat to `experiments/status/<run_id>.json` every few seconds. It is the
**liveness signal** for multi-day sessions of hundreds of experiments:

- **time budget** — a run exceeding `time_budget_seconds` is terminated
  (`state: timeout`). This is Karpathy's "fixed budget per run" rule.
- **stall detection** — a run producing no output for `stall_timeout_seconds`
  is treated as hung and terminated (`state: stalled`).
- watch progress with `autoresearch status`; it exits non-zero and lists any
  run whose state is `stalled` or `timeout`, so a supervising loop can react.

## CLI

```
autoresearch hypothesize <project_id> --count 8 [--goal "..."]   # ResearchAgent
autoresearch plan        ideas/example_idea.md
autoresearch validate    experiments/contracts/<run>.yaml [--repo PATH]
autoresearch run         <run_id> --cmd "..." --time-budget 300 --stall-timeout 60
autoresearch status
autoresearch analyze     experiments/contracts/<run>.yaml experiments/logs/<run>.json
autoresearch review      <run_id>   |   autoresearch review --all             # ReviewAgent
```
