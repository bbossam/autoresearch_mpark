from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from .models import IdeaSpec


ModelT = TypeVar("ModelT", bound=BaseModel)


def load_yaml_model(path: str | Path, model_type: type[ModelT]) -> ModelT:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return model_type.model_validate(data)


def write_yaml(data: object, path: str | Path) -> Path:
    """Serialize a plain dict/list to a YAML file, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def load_idea(path: str | Path) -> IdeaSpec:
    """Load an IdeaSpec from a YAML file, or a Markdown file with YAML frontmatter.

    Everything after the frontmatter is kept as the idea's `notes`.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    body = ""
    stripped = text.lstrip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) == 3:
            data = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            data = yaml.safe_load(stripped) or {}
    else:
        data = yaml.safe_load(text) or {}
    if isinstance(data, dict) and body and "notes" not in data:
        data["notes"] = body
    return IdeaSpec.model_validate(data)


def write_idea(idea: IdeaSpec, path: str | Path) -> Path:
    """Write an IdeaSpec as a Markdown file with YAML frontmatter."""
    data = idea.model_dump(mode="json", exclude_defaults=True)
    notes = data.pop("notes", "")
    front = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    body = f"\n{notes}\n" if notes else ""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}---\n{body}", encoding="utf-8")
    return path

