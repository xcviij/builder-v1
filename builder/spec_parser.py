"""
spec_parser.py

Responsibility: Load and parse a spec markdown file into a deterministic, typed model.

This implementation intentionally stays conservative:
- It prefers YAML frontmatter at the top of the markdown file.
- It can fall back to a tiny "key: value" parser (best-effort).

The renderer and CLI should treat the parsed result as the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class GitHubSpec:
    """GitHub-related configuration parsed from the spec."""

    owner: str | None = None
    private: bool = True


@dataclass(frozen=True)
class Spec:
    """Parsed spec contents used to render a template and create a GitHub repo."""

    repo_name: str
    description: str = ""
    template: str = "fastapi-api"
    github: GitHubSpec = field(default_factory=GitHubSpec)
    variables: dict[str, Any] = field(default_factory=dict)


def _parse_yaml_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """
    If the markdown begins with YAML frontmatter delimited by '---', parse it.
    Returns (frontmatter_dict_or_none, remaining_markdown_text).
    """
    if not text.startswith("---\n"):
        return None, text

    # Find the closing delimiter.
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SpecError("YAML frontmatter starts with '---' but no closing '---' was found.")

    fm_text = text[4:end]  # between delimiters
    rest = text[end + len("\n---\n") :]
    data = yaml.safe_load(fm_text) or {}
    if not isinstance(data, dict):
        raise SpecError("YAML frontmatter must be a mapping/object at the top level.")
    return data, rest


def _best_effort_kv_parse(text: str) -> dict[str, Any]:
    """
    Very small fallback parser:
    - Reads lines like `key: value` (ignores markdown headings and empty lines)
    - Stops at the first blank line after having found at least one key/value pair
    """
    out: dict[str, Any] = {}
    found_any = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if found_any and not line:
                break
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        found_any = True
        out[k] = v
    return out


def parse_spec(spec_path: str | Path) -> Spec:
    """
    Parse a markdown spec file into a `Spec`.

    Expected (recommended) YAML frontmatter keys:
    - repo_name: str (required)
    - description: str
    - template: str
    - github.owner: str
    - github.private: bool
    - variables: dict (optional additional values for templates)
    """
    path = Path(spec_path)
    if not path.exists():
        raise SpecError(f"Spec file does not exist: {path}")
    text = path.read_text(encoding="utf-8")

    frontmatter, _rest = _parse_yaml_frontmatter(text)
    data = frontmatter if frontmatter is not None else _best_effort_kv_parse(text)

    repo_name = str(data.get("repo_name") or data.get("name") or "").strip()
    if not repo_name:
        raise SpecError("Spec must define `repo_name` (YAML frontmatter recommended).")

    description = str(data.get("description") or "").strip()
    template = str(data.get("template") or "fastapi-api").strip()

    gh_raw = data.get("github") or {}
    if gh_raw is None:
        gh_raw = {}
    if not isinstance(gh_raw, dict):
        raise SpecError("`github` must be an object/mapping when provided.")

    owner = gh_raw.get("owner")
    if owner is not None:
        owner = str(owner).strip() or None

    private_raw = gh_raw.get("private", True)
    private = bool(private_raw)

    vars_raw = data.get("variables") or {}
    if vars_raw is None:
        vars_raw = {}
    if not isinstance(vars_raw, dict):
        raise SpecError("`variables` must be an object/mapping when provided.")

    # Ensure deterministic ordering at the boundary (renderer may rely on stable keys).
    variables = dict(sorted(vars_raw.items(), key=lambda kv: str(kv[0])))

    return Spec(
        repo_name=repo_name,
        description=description,
        template=template,
        github=GitHubSpec(owner=owner, private=private),
        variables=variables,
    )


