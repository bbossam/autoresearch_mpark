# AutoresearchByMpark

A general, stable **control plane** for agent-driven autoresearch: it plans,
validates, runs, and analyses experiments across multiple target projects on
this machine — without ever holding their code.

## Design

- **Control plane, not a workbench.** Target projects are referenced by path
  through capsules in `configs/project_capsules/`.
- **Pure agents, single execution layer.** Agents decide; the CLI and watchdog
  act. (Intelligence/execution split — OpenHarness.)
- **Hill-climbing.** A run counts as progress only if it beats the recorded
  best for its metric. (Karpathy autoresearch.)
- **Watchdog.** Long unattended runs emit heartbeats and are killed on timeout
  or stall, so hundreds of overnight experiments never hang silently.

## Agents

| Agent | Role |
|-------|------|
| ResearchAgent | aggressively hypothesise ideas for an early-stage project (Codex) |
| PlanningAgent | research idea → file-scoped RunContract |
| ValidationAgent | gatekeeper: contract consistency + diff audit |
| ImplementationAgent | apply change to target repo (stub in v0) |
| AnalysisAgent | judge metrics vs accept rules, render report, update leaderboard |
| ReviewAgent | Codex-review a run's logs/reports, triage keep/flag/discard |

See [AGENTS.md](AGENTS.md) for the full pipeline.

## Layout

```
src/autoresearch/   agents/, watchdog.py, models.py, leaderboard.py, metrics.py, ...
configs/project_capsules/   one YAML per target project
ideas/              research ideas (Markdown + YAML frontmatter)
experiments/        contracts/  logs/  status/  reports/  leaderboard.json
knowledge/          durable accumulated findings
```

## Quickstart

```bash
pip install -e ".[test]"
pytest

# 0. hypothesise ideas for an early-stage project (Codex)
autoresearch hypothesize example_project --count 8 --goal "cut training time"

# 1. plan: idea -> run contract
autoresearch plan ideas/example_idea.md

# 2. validate the contract (and optionally a target-repo diff)
autoresearch validate experiments/contracts/<run_id>.yaml --repo /path/to/repo

# 3. run an experiment under the watchdog (time budget + stall detection)
autoresearch run <run_id> --cmd "python train.py" --time-budget 300 --stall-timeout 60

# 4. watch status across all runs (safe to poll on a loop)
autoresearch status

# 5. analyse results against accept rules + the leaderboard
autoresearch analyze experiments/contracts/<run_id>.yaml experiments/logs/<run_id>.json

# 6. Codex-review the run (or all runs) into a compact verdict
autoresearch review <run_id>
```

Codex-backed steps (`hypothesize`, `review`) need the `codex` CLI on PATH;
override the invocation with `AUTORESEARCH_CODEX_CMD`.

## Safety

- no LLM calls; `ImplementationAgent` performs no writes in v0
- only `ImplementerAgent` may hold `may_write=true` in a contract
- evaluation code, datasets, and benchmarks are forbidden by default
