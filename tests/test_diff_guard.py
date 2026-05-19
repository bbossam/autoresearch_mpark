from __future__ import annotations

import subprocess
from pathlib import Path

from autoresearch.diff_guard import audit_diff
from autoresearch.models import RunContract


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "src").mkdir()
    (repo / "eval").mkdir()
    (repo / "src" / "allowed.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "eval" / "metric.py").write_text("score = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _contract(**kwargs) -> RunContract:
    data = {
        "run_id": "r1",
        "target_project": "p1",
        "hypothesis": "A constrained change helps.",
        "primary_metric": "score",
        "allowed_files": ["src/**"],
        "forbidden_files": ["eval/**", "datasets/**", "benchmarks/**", "shared/**"],
        "max_files_changed": 5,
        "max_lines_changed": 20,
    }
    data.update(kwargs)
    return RunContract.model_validate(data)


def test_diff_guard_passes_allowed_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "src" / "allowed.py").write_text("x = 2\n", encoding="utf-8")

    audit = audit_diff(_contract(), repo)

    assert audit.passed
    assert audit.changed_files == ["src/allowed.py"]
    assert audit.rejection_reasons == []


def test_diff_guard_rejects_forbidden_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "eval" / "metric.py").write_text("score = 2\n", encoding="utf-8")

    audit = audit_diff(_contract(allowed_files=["src/**", "eval/**"]), repo)

    assert not audit.passed
    assert "eval/metric.py" in audit.changed_files
    assert any("forbidden_files" in reason for reason in audit.rejection_reasons)


def test_diff_guard_rejects_too_many_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    for idx in range(3):
        path = repo / "src" / f"file_{idx}.py"
        path.write_text(f"x = {idx}\n", encoding="utf-8")
        _git(repo, "add", str(path.relative_to(repo)))
        _git(repo, "commit", "-m", f"add file {idx}")
        path.write_text(f"x = {idx + 10}\n", encoding="utf-8")

    audit = audit_diff(_contract(max_files_changed=2), repo)

    assert not audit.passed
    assert len(audit.changed_files) == 3
    assert any("max_files_changed exceeded" in reason for reason in audit.rejection_reasons)


def test_diff_guard_catches_staged_and_untracked_files(tmp_path: Path):
    repo = _init_repo(tmp_path)
    # a brand-new untracked forbidden file
    (repo / "eval" / "new_metric.py").write_text("m = 1\n", encoding="utf-8")
    # a git-added (staged) forbidden file
    staged = repo / "eval" / "staged_metric.py"
    staged.write_text("s = 1\n", encoding="utf-8")
    _git(repo, "add", "eval/staged_metric.py")

    audit = audit_diff(_contract(allowed_files=["src/**", "eval/**"]), repo)

    assert "eval/new_metric.py" in audit.changed_files
    assert "eval/staged_metric.py" in audit.changed_files
    assert not audit.passed
    assert audit.total_lines_changed >= 2

