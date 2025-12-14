"""
renderer.py

Responsibility: Deterministically render/copy a template directory into a destination.

Rules:
- Walk template files in sorted order to ensure deterministic output.
- Copy files exactly as they exist in the template directory.
- For UTF-8 text files, if Jinja2 markers are present, render with the provided context.
- Non-text/binary files are copied byte-for-byte.

This module intentionally does NOT know about GitHub, git, or CLI parsing.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    rendered_files: int
    copied_files: int


def _is_binary_file(path: Path) -> bool:
    """
    Best-effort: treat a file as binary if it cannot be decoded as UTF-8.
    """
    try:
        path.read_text(encoding="utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _iter_template_files(template_dir: Path) -> list[Path]:
    """
    Return all files under template_dir, in deterministic lexicographic order
    (relative path ordering).
    """
    files: list[Path] = []
    for root, _dirs, filenames in os.walk(template_dir):
        root_path = Path(root)
        for name in filenames:
            files.append(root_path / name)
    files.sort(key=lambda p: str(p.relative_to(template_dir)).replace(os.sep, "/"))
    return files


def render_template_dir(
    *,
    template_dir: str | Path,
    destination_dir: str | Path,
    context: dict[str, Any],
) -> RenderResult:
    """
    Render/copy a template directory into destination_dir.

    - Creates destination directories as needed.
    - Copies file permissions from template files.
    """
    tpl_dir = Path(template_dir).resolve()
    dst_dir = Path(destination_dir).resolve()

    if not tpl_dir.exists() or not tpl_dir.is_dir():
        raise RenderError(f"Template directory not found: {tpl_dir}")

    env = Environment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    rendered = 0
    copied = 0

    for src_path in _iter_template_files(tpl_dir):
        rel = src_path.relative_to(tpl_dir)
        dst_path = dst_dir / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy binary files byte-for-byte.
        if _is_binary_file(src_path):
            shutil.copy2(src_path, dst_path)
            copied += 1
            continue

        text = src_path.read_text(encoding="utf-8")
        if ("{{" in text) or ("{%" in text) or ("{#" in text):
            try:
                template = env.from_string(text)
                out = template.render(**context)
            except Exception as e:  # noqa: BLE001 - surface as RenderError
                raise RenderError(f"Failed rendering template file: {rel}") from e
            # For rendered output, normalize newlines for stable cross-platform output.
            dst_path.write_text(out, encoding="utf-8", newline="\n")
            shutil.copystat(src_path, dst_path)
            rendered += 1
        else:
            # Exact copy for non-templated files (preserve bytes as authored in template).
            shutil.copy2(src_path, dst_path)
            copied += 1

    return RenderResult(rendered_files=rendered, copied_files=copied)


