from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .agents import (
    AgentOutcome,
    AnalysisAgent,
    ContextAgent,
    PlanningAgent,
    ResearchAgent,
    ResearchContext,
    ResourceAgent,
    ResourceRequest,
    ReviewAgent,
    ReviewArtifacts,
    SessionSnapshot,
    ValidationAgent,
)
from .codex_client import CodexError, run_codex
from .dashboard import serve
from .diff_guard import audit_diff
from .io import load_idea, load_yaml_model, write_idea, write_yaml
from .leaderboard import Leaderboard
from .logger import write_run_result
from .mistakes import MistakeLedger
from .models import ProjectCapsule, RunContract, RunResult
from .registry import MachineRegistry, ProjectRegistry
from .remote import probe_machine
from .tokens import check_budget, clip_to_tokens
from .watchdog import run_with_watchdog


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _load_project(path: str) -> ProjectCapsule:
    return load_yaml_model(path, ProjectCapsule)


def _load_run(path: str) -> RunContract:
    return load_yaml_model(path, RunContract)


def _outcome_dict(outcome: AgentOutcome) -> dict:
    return {
        "agent": outcome.agent,
        "ok": outcome.ok,
        "summary": outcome.summary,
        "issues": outcome.issues,
        "data": outcome.data,
    }


# --- schema / audit commands -------------------------------------------------


def cmd_validate_project(args: argparse.Namespace) -> int:
    capsule = _load_project(args.capsule)
    _print_json({"ok": True, "project_id": capsule.project_id, "name": capsule.name})
    return 0


def cmd_validate_run(args: argparse.Namespace) -> int:
    contract = _load_run(args.run_contract)
    _print_json(
        {
            "ok": True,
            "run_id": contract.run_id,
            "target_project": contract.target_project,
            "primary_metric": contract.primary_metric,
        }
    )
    return 0


def cmd_audit_diff(args: argparse.Namespace) -> int:
    contract = _load_run(args.run_contract)
    audit = audit_diff(contract, args.repo)
    _print_json(
        {
            "ok": audit.passed,
            "changed_files": audit.changed_files,
            "total_lines_changed": audit.total_lines_changed,
            "rejection_reasons": audit.rejection_reasons,
        }
    )
    return 0 if audit.passed else 2


def cmd_dry_run(args: argparse.Namespace) -> int:
    contract_path = Path(args.run_contract)
    contract = _load_run(contract_path)

    registry_root = contract_path.parent.parent.parent / "configs" / "project_capsules"
    if not registry_root.exists():
        registry_root = Path("configs/project_capsules")
    registry = ProjectRegistry.load(registry_root)

    reasons: list[str] = []
    try:
        registry.get(contract.target_project)
    except KeyError as exc:
        reasons.append(str(exc))

    result = RunResult(
        run_id=contract.run_id,
        target_project=contract.target_project,
        status="dry_run" if not reasons else "rejected",
        accepted=False,
        modified_files=[],
        metrics={},
        rejection_reasons=reasons,
    )
    log_path = write_run_result(result, contract.log_dir)
    _print_json(
        {
            "ok": not reasons,
            "run_id": contract.run_id,
            "target_project": contract.target_project,
            "log_path": str(log_path),
            "rejection_reasons": reasons,
            "note": "dry-run only; no agents executed and no target project files modified",
        }
    )
    return 0 if not reasons else 2


# --- agent-driven commands ---------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    idea = load_idea(args.idea)
    registry = ProjectRegistry.load(args.capsules)
    capsule = registry.get(idea.target_project)
    contract = PlanningAgent().plan(idea, capsule, run_id=args.run_id)
    path = write_yaml(
        contract.model_dump(mode="json"),
        Path(args.out_dir) / f"{contract.run_id}.yaml",
    )
    _print_json(
        {
            "ok": True,
            "run_id": contract.run_id,
            "target_project": contract.target_project,
            "contract_path": str(path),
        }
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    contract = _load_run(args.run_contract)
    registry = ProjectRegistry.load(args.capsules)
    agent = ValidationAgent()
    checks = [agent.validate_contract(contract, registry)]
    if args.repo:
        checks.append(agent.validate_diff(contract, args.repo))
    ok = all(c.ok for c in checks)
    _print_json({"ok": ok, "checks": [_outcome_dict(c) for c in checks]})
    return 0 if ok else 2


def cmd_analyze(args: argparse.Namespace) -> int:
    contract = _load_run(args.run_contract)
    result = RunResult.model_validate(
        json.loads(Path(args.result).read_text(encoding="utf-8"))
    )
    mismatch: list[str] = []
    if result.run_id != contract.run_id:
        mismatch.append(
            f"result run_id {result.run_id!r} != contract {contract.run_id!r}"
        )
    if result.target_project != contract.target_project:
        mismatch.append(
            f"result target_project {result.target_project!r} != "
            f"contract {contract.target_project!r}"
        )
    if mismatch:
        _print_json({"ok": False, "errors": mismatch})
        return 2
    agent = AnalysisAgent()
    board = Leaderboard(args.leaderboard)
    prior = board.best(contract.target_project, contract.primary_metric)
    outcome = agent.analyze(
        contract, result, prior_best=prior["value"] if prior else None
    )
    report = agent.render_report(contract, result, outcome)
    report_path = Path(args.reports_dir) / f"{contract.run_id}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    new_best = False
    primary = result.metrics.get(contract.primary_metric)
    if outcome.ok and primary is not None:
        new_best = board.record(
            contract.target_project,
            contract.primary_metric,
            primary,
            contract.run_id,
            outcome.data.get("primary_higher_is_better"),
        )
        board.save()

    if not outcome.ok:
        ledger = MistakeLedger(args.mistakes)
        ledger.record(
            contract.run_id,
            contract.target_project,
            contract.hypothesis,
            "; ".join(outcome.issues) or "rejected by accept rules",
            source="analyze",
        )
        ledger.save()

    _print_json(
        {
            "ok": outcome.ok,
            "run_id": contract.run_id,
            "verdict": "accepted" if outcome.ok else "rejected",
            "new_best": new_best,
            "beats_best": outcome.data.get("beats_best"),
            "report_path": str(report_path),
            "issues": outcome.issues,
        }
    )
    return 0 if outcome.ok else 2


# --- watchdog commands -------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    result = run_with_watchdog(
        args.run_id,
        args.cmd,
        cwd=args.cwd,
        time_budget_seconds=args.time_budget,
        stall_timeout_seconds=args.stall_timeout,
        heartbeat_seconds=args.heartbeat,
    )
    _print_json(
        {
            "ok": result.state == "completed",
            "run_id": result.run_id,
            "state": result.state,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "status_path": str(result.status_path),
            "log_path": str(result.log_path),
        }
    )
    return 0 if result.state == "completed" else 2


def cmd_status(args: argparse.Namespace) -> int:
    status_dir = Path(args.status_dir)
    runs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(status_dir.glob("*.json"))
    ]
    hung = [r["run_id"] for r in runs if r["state"] in ("stalled", "timeout")]
    running = [r["run_id"] for r in runs if r["state"] == "running"]
    _print_json(
        {
            "ok": not hung,
            "count": len(runs),
            "running": running,
            "hung": hung,
            "runs": runs,
        }
    )
    return 0 if not hung else 2


# --- review & research commands (Codex-backed) ------------------------------


def _review_run_ids(args: argparse.Namespace) -> list[str]:
    if args.run_id:
        return [args.run_id]
    logs = Path(args.logs_dir)
    reviews = Path(args.reviews_dir)
    ids = {p.stem for p in logs.glob("*.out")} | {p.stem for p in logs.glob("*.json")}
    run_ids = sorted(ids)
    if not args.force:
        run_ids = [r for r in run_ids if not (reviews / f"{r}.md").exists()]
    return run_ids


def _gather_review_artifacts(
    run_id: str, args: argparse.Namespace
) -> ReviewArtifacts:
    logs = Path(args.logs_dir)
    target_project = ""
    hypothesis = ""
    primary_metric = ""
    metrics: dict[str, float] = {}

    contract_path = Path(args.contracts_dir) / f"{run_id}.yaml"
    if contract_path.exists():
        contract = _load_run(contract_path)
        target_project = contract.target_project
        hypothesis = contract.hypothesis
        primary_metric = contract.primary_metric

    result_path = logs / f"{run_id}.json"
    if result_path.exists():
        metrics = RunResult.model_validate(
            json.loads(result_path.read_text(encoding="utf-8"))
        ).metrics

    log_excerpt = ""
    out_path = logs / f"{run_id}.out"
    if out_path.exists():
        raw_log = out_path.read_text(encoding="utf-8", errors="replace")
        log_excerpt, _ = clip_to_tokens(raw_log, args.max_log_tokens)

    report = ""
    report_path = Path(args.reports_dir) / f"{run_id}.md"
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")

    return ReviewArtifacts(
        run_id=run_id,
        target_project=target_project,
        hypothesis=hypothesis,
        primary_metric=primary_metric,
        metrics=metrics,
        log_excerpt=log_excerpt,
        report=report,
    )


def cmd_review(args: argparse.Namespace) -> int:
    if not args.run_id and not args.all:
        print("error: specify a run_id, or pass --all", file=sys.stderr)
        return 2
    agent = ReviewAgent()
    run_ids = _review_run_ids(args)
    if not run_ids:
        _print_json({"ok": True, "count": 0, "reviews": [], "note": "nothing to review"})
        return 0

    reviews: list[dict] = []
    ledger = MistakeLedger(args.mistakes)
    recorded = False
    failures = 0
    for run_id in run_ids:
        artifacts = _gather_review_artifacts(run_id, args)
        prompt = agent.build_prompt(artifacts)
        check = check_budget(prompt, args.token_budget)
        if not check.fits:
            failures += 1
            reviews.append(
                {
                    "run_id": run_id,
                    "ok": False,
                    "prompt_tokens": check.estimated,
                    "error": (
                        f"prompt ~{check.estimated} tokens exceeds budget "
                        f"{check.budget}; lower --max-log-tokens"
                    ),
                }
            )
            continue
        try:
            outcome = agent.review(
                artifacts, lambda p: run_codex(p, timeout=args.timeout)
            )
        except CodexError as exc:
            failures += 1
            reviews.append({"run_id": run_id, "ok": False, "error": str(exc)})
            continue
        review_path = Path(args.reviews_dir) / f"{run_id}.md"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            agent.render_review(artifacts, outcome), encoding="utf-8"
        )
        if outcome.data["verdict"] == "discard":
            ledger.record(
                run_id,
                artifacts.target_project,
                artifacts.hypothesis,
                outcome.data.get("summary") or "discarded by review",
                source="review",
            )
            recorded = True
        reviews.append(
            {
                "run_id": run_id,
                "ok": True,
                "verdict": outcome.data["verdict"],
                "interesting": outcome.data["interesting"],
                "prompt_tokens": check.estimated,
                "review_path": str(review_path),
            }
        )
    if recorded:
        ledger.save()
    _print_json({"ok": failures == 0, "count": len(reviews), "reviews": reviews})
    return 0 if failures == 0 else 2


def cmd_hypothesize(args: argparse.Namespace) -> int:
    registry = ProjectRegistry.load(args.capsules)
    capsule = registry.get(args.project_id)

    out_dir = Path(args.out_dir)
    existing = sorted(p.stem for p in out_dir.glob("*.md") if p.stem != "TEMPLATE")
    findings_path = Path(args.findings)
    prior_findings = ""
    if findings_path.exists():
        prior_findings, _ = clip_to_tokens(
            findings_path.read_text(encoding="utf-8"), 1500
        )

    context = ResearchContext(
        project_id=capsule.project_id,
        project_name=capsule.name,
        description=capsule.description,
        notes=capsule.notes,
        goal=args.goal or "",
        existing_idea_ids=existing,
        prior_findings=prior_findings,
        known_failures=MistakeLedger(args.mistakes).as_prompt_text(capsule.project_id),
    )
    agent = ResearchAgent()
    try:
        ideas, outcome = agent.hypothesize(
            context,
            lambda p: run_codex(p, timeout=args.timeout),
            count=args.count,
        )
    except CodexError as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 2

    created = [str(write_idea(idea, out_dir / f"{idea.idea_id}.md")) for idea in ideas]
    _print_json(
        {
            "ok": outcome.ok,
            "count": len(created),
            "created": created,
            "issues": outcome.issues,
        }
    )
    return 0 if outcome.ok else 2


# --- session context (cross-session memory) ---------------------------------


def _parse_review_verdict(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("- verdict:"):
            return stripped.split(":", 1)[1].strip()
    return "unknown"


def _gather_snapshot(args: argparse.Namespace) -> SessionSnapshot:
    leaderboard = Leaderboard(args.leaderboard).entries()
    statuses = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(Path(args.status_dir).glob("*.json"))
    ]
    contracts_dir = Path(args.contracts_dir)
    contract_ids = sorted(p.stem for p in contracts_dir.glob("*.yaml"))
    planned: set[str] = set()
    for path in contracts_dir.glob("*.yaml"):
        try:
            idea_id = _load_run(path).metadata.get("idea_id")
        except (ValidationError, OSError, ValueError):
            continue
        if idea_id:
            planned.add(str(idea_id))
    idea_ids: list[str] = []
    for path in sorted(Path(args.ideas_dir).glob("*.md")):
        if path.stem == "TEMPLATE":
            continue
        try:
            idea_ids.append(load_idea(path).idea_id)
        except (ValidationError, OSError, ValueError):
            idea_ids.append(path.stem)
    pending_ideas = sorted(i for i in idea_ids if i not in planned)
    results = sorted(p.stem for p in Path(args.logs_dir).glob("*.json"))
    reviews = [
        {
            "run_id": p.stem,
            "verdict": _parse_review_verdict(p.read_text(encoding="utf-8")),
        }
        for p in sorted(Path(args.reviews_dir).glob("*.md"))
    ]
    mistakes = MistakeLedger(args.mistakes).all()
    return SessionSnapshot(
        leaderboard=leaderboard,
        statuses=statuses,
        pending_ideas=pending_ideas,
        contracts=contract_ids,
        results=results,
        recent_reviews=reviews,
        mistakes=mistakes,
    )


def cmd_resume(args: argparse.Namespace) -> int:
    outcome = ContextAgent().brief(_gather_snapshot(args))
    briefing = outcome.data["briefing"]
    session_path = Path(args.context_dir) / "session.md"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(briefing, encoding="utf-8")
    print(briefing)
    return 0 if outcome.ok else 2


# --- remote machines & resources --------------------------------------------


def cmd_machines(args: argparse.Namespace) -> int:
    registry = MachineRegistry.load(args.machines_dir)
    rows: list[dict] = []
    for machine in registry.all():
        row: dict = {
            "machine_id": machine.machine_id,
            "name": machine.name,
            "ssh_target": machine.ssh_target or "(local)",
            "scheduler": machine.scheduler,
            "gpus": machine.gpus,
            "env": machine.env.kind.value,
        }
        if args.probe:
            state = probe_machine(machine, timeout=args.timeout)
            row["reachable"] = state.reachable
            if state.reachable:
                row["gpu_state"] = [
                    {
                        "index": g.index,
                        "mem_free_mb": g.mem_free_mb,
                        "util_pct": g.util_pct,
                    }
                    for g in state.gpus
                ]
                row["disk_free_gb"] = state.disk_free_gb
            else:
                row["note"] = state.note
        rows.append(row)
    _print_json({"ok": True, "count": len(rows), "machines": rows})
    return 0


def cmd_place(args: argparse.Namespace) -> int:
    registry = MachineRegistry.load(args.machines_dir)
    machines = registry.all()
    if not machines:
        _print_json(
            {"ok": False, "error": f"no machines registered in {args.machines_dir}"}
        )
        return 2
    states = [probe_machine(m, timeout=args.timeout) for m in machines]
    request = ResourceRequest(
        gpus_needed=args.gpus,
        min_free_gpu_mb=args.min_gpu_mb,
        min_disk_gb=args.min_disk_gb,
    )
    outcome = ResourceAgent().place(states, request)
    _print_json(
        {
            "ok": outcome.ok,
            "summary": outcome.summary,
            "placement": outcome.data.get("placement"),
            "issues": outcome.issues,
        }
    )
    return 0 if outcome.ok else 2


def cmd_dashboard(args: argparse.Namespace) -> int:
    serve(host=args.host, port=args.port, leaderboard_path=args.leaderboard)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoresearch")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate-project", help="schema-check a project capsule")
    p.add_argument("capsule")
    p.set_defaults(func=cmd_validate_project)

    p = sub.add_parser("validate-run", help="schema-check a run contract")
    p.add_argument("run_contract")
    p.set_defaults(func=cmd_validate_run)

    p = sub.add_parser("audit-diff", help="audit a target repo diff against a contract")
    p.add_argument("run_contract")
    p.add_argument("--repo", required=True)
    p.set_defaults(func=cmd_audit_diff)

    p = sub.add_parser("dry-run", help="dry-run a contract; no agents execute")
    p.add_argument("run_contract")
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("plan", help="PlanningAgent: idea -> run contract")
    p.add_argument("idea")
    p.add_argument("--capsules", default="configs/project_capsules")
    p.add_argument("--out-dir", default="experiments/contracts")
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("validate", help="ValidationAgent: check a contract (and diff)")
    p.add_argument("run_contract")
    p.add_argument("--capsules", default="configs/project_capsules")
    p.add_argument("--repo", default=None)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("analyze", help="AnalysisAgent: judge a run result")
    p.add_argument("run_contract")
    p.add_argument("result", help="path to a RunResult JSON file")
    p.add_argument("--reports-dir", default="experiments/reports")
    p.add_argument("--leaderboard", default="experiments/leaderboard.json")
    p.add_argument("--mistakes", default="experiments/mistakes.json")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("run", help="run an experiment command under the watchdog")
    p.add_argument("run_id")
    p.add_argument("--cmd", required=True, help="experiment command to run")
    p.add_argument("--cwd", default=None)
    p.add_argument("--time-budget", type=float, default=300.0)
    p.add_argument("--stall-timeout", type=float, default=60.0)
    p.add_argument("--heartbeat", type=float, default=10.0)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="show watchdog status for all runs")
    p.add_argument("--status-dir", default="experiments/status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("review", help="ReviewAgent: Codex-review run artifacts")
    p.add_argument("run_id", nargs="?", default=None, help="run to review; omit with --all")
    p.add_argument("--all", action="store_true", help="review every run lacking a review")
    p.add_argument("--force", action="store_true", help="re-review runs already reviewed")
    p.add_argument("--logs-dir", default="experiments/logs")
    p.add_argument("--reports-dir", default="experiments/reports")
    p.add_argument("--contracts-dir", default="experiments/contracts")
    p.add_argument("--reviews-dir", default="experiments/reviews")
    p.add_argument("--max-log-tokens", type=int, default=4000)
    p.add_argument("--token-budget", type=int, default=120000)
    p.add_argument("--mistakes", default="experiments/mistakes.json")
    p.add_argument("--timeout", type=float, default=300.0)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("hypothesize", help="ResearchAgent: aggressively generate ideas")
    p.add_argument("project_id")
    p.add_argument("--count", type=int, default=8)
    p.add_argument("--goal", default=None)
    p.add_argument("--capsules", default="configs/project_capsules")
    p.add_argument("--out-dir", default="ideas")
    p.add_argument("--findings", default="knowledge/findings.md")
    p.add_argument("--mistakes", default="experiments/mistakes.json")
    p.add_argument("--timeout", type=float, default=300.0)
    p.set_defaults(func=cmd_hypothesize)

    p = sub.add_parser("resume", help="ContextAgent: briefing of where things stand")
    p.add_argument("--leaderboard", default="experiments/leaderboard.json")
    p.add_argument("--status-dir", default="experiments/status")
    p.add_argument("--contracts-dir", default="experiments/contracts")
    p.add_argument("--ideas-dir", default="ideas")
    p.add_argument("--logs-dir", default="experiments/logs")
    p.add_argument("--reviews-dir", default="experiments/reviews")
    p.add_argument("--mistakes", default="experiments/mistakes.json")
    p.add_argument("--context-dir", default="experiments/context")
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("machines", help="list registered remote machines")
    p.add_argument("--machines-dir", default="configs/machines")
    p.add_argument("--probe", action="store_true", help="query live GPU/disk over SSH")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(func=cmd_machines)

    p = sub.add_parser("place", help="ResourceAgent: pick a machine for a run")
    p.add_argument("--machines-dir", default="configs/machines")
    p.add_argument("--gpus", type=int, default=1)
    p.add_argument("--min-gpu-mb", type=int, default=0)
    p.add_argument("--min-disk-gb", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(func=cmd_place)

    p = sub.add_parser("dashboard", help="serve the leaderboard web dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--leaderboard", default="experiments/leaderboard.json")
    p.set_defaults(func=cmd_dashboard)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    except (OSError, KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
