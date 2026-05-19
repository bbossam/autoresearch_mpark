# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

## What this project is

A **control plane** for automated research — it plans, validates, runs, and
analyses experiments against *other* projects on this machine. Target project
code never lives here. See `AGENTS.md` for the full design.

## Rules

- Never add a target project's source into this repo. Reference it through a
  capsule in `configs/project_capsules/`.
- Agents (`src/autoresearch/agents/`) stay **pure** — no file I/O, no
  subprocess calls. All I/O belongs in `cli.py` or `watchdog.py`.
- Only `ImplementerAgent` may have `may_write=true` in a contract.
- `experiments/logs/`, `experiments/status/`, and `experiments/reports/` are
  generated run artefacts — don't hand-edit them.
- Long or unattended runs must go through the watchdog so hangs are caught.

## Commands

```bash
pip install -e ".[test]"
pytest                       # run the test suite
autoresearch --help          # all subcommands
```

## Layout

- `src/autoresearch/agents/` — one file per agent, one role each
- `src/autoresearch/watchdog.py` — subprocess monitor (time budget + stall)
- `src/autoresearch/leaderboard.py` — best-metric-so-far (hill-climbing memory)
- `configs/project_capsules/` — one YAML per target project
- `ideas/` — research ideas (Markdown + YAML frontmatter)
- `experiments/` — `contracts/`, `logs/`, `status/`, `reports/`, `leaderboard.json`
- `knowledge/findings.md` — durable accumulated lessons
