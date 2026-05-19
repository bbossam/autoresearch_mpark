from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import RunContract


@dataclass
class DiffAudit:
    passed: bool
    changed_files: list[str] = field(default_factory=list)
    total_lines_changed: int = 0
    rejection_reasons: list[str] = field(default_factory=list)


def _run_git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def git_changed_files(repo: str | Path) -> list[str]:
    """All changed paths — staged, unstaged, and untracked.

    Uses ``git status --porcelain`` so git-added or brand-new untracked files
    are not invisible to the gatekeeper.
    """
    repo = Path(repo)
    out = _run_git(repo, ["status", "--porcelain", "--untracked-files=all"])
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        if " -> " in path:  # rename: "old -> new"
            path = path.split(" -> ", 1)[1]
        files.append(path.strip().strip('"'))
    return files


def git_total_lines_changed(repo: str | Path) -> int:
    """Lines changed across staged + unstaged tracked files and untracked files."""
    repo = Path(repo)
    total = 0
    try:
        numstat = _run_git(repo, ["diff", "HEAD", "--numstat"])
    except subprocess.CalledProcessError:
        numstat = _run_git(repo, ["diff", "--numstat"])
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted = parts[0], parts[1]
        if added == "-" or deleted == "-":
            total += 1
        else:
            total += int(added) + int(deleted)
    untracked = _run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    for rel in untracked.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(text.splitlines())
    return total


def _matches(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        pat = pattern.replace("\\", "/")
        if pat.endswith("/"):
            if normalized.startswith(pat):
                return True
        elif fnmatch.fnmatch(normalized, pat) or normalized == pat:
            return True
    return False


def audit_diff(contract: RunContract, repo: str | Path) -> DiffAudit:
    changed_files = git_changed_files(repo)
    total_lines = git_total_lines_changed(repo)
    reasons: list[str] = []

    for path in changed_files:
        if not _matches(path, contract.allowed_files):
            reasons.append(f"changed file outside allowed_files: {path}")
        if _matches(path, contract.forbidden_files):
            reasons.append(f"changed file matches forbidden_files: {path}")

    if len(changed_files) > contract.max_files_changed:
        reasons.append(
            f"max_files_changed exceeded: {len(changed_files)} > "
            f"{contract.max_files_changed}"
        )

    if total_lines > contract.max_lines_changed:
        reasons.append(
            f"max_lines_changed exceeded: {total_lines} > "
            f"{contract.max_lines_changed}"
        )

    return DiffAudit(
        passed=not reasons,
        changed_files=changed_files,
        total_lines_changed=total_lines,
        rejection_reasons=reasons,
    )

