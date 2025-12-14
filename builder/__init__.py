"""
builder package

This package implements Builder v1 as a CLI-first utility.

Key responsibilities are split across modules:
- `spec_parser.py`: parse markdown spec input into a structured configuration
- `renderer.py`: deterministic template rendering/copying into an output directory
- `github_client.py`: isolated GitHub REST API interactions (repo creation / lookup)
- `cli.py`: CLI entrypoint and orchestration (parse -> render -> git -> push)
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"


