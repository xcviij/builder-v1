## builder-v1 (Python CLI)

This repository contains **Builder v1**, a Python 3.11+ CLI utility that:

- Reads a **spec markdown** file
- Loads a project **template** from `templates/`
- Renders files **deterministically**
- Creates a **new GitHub repository** (GitHub REST API)
- Initializes git, commits, and pushes to `main`

### Non-goals

- No FastAPI server (this tool is a CLI)
- No UI
- No database

### Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Usage

```bash
python -m builder.cli build path/to/spec.md \
  --github-owner your-org-or-user \
  --github-token "$GITHUB_TOKEN"
```

Common flags:

- `--template fastapi-api`: template name under `templates/`
- `--workdir ./generated/<name>`: where to render + run git operations
- `--overwrite`: allow using a non-empty `--workdir`
- `--skip-github`: render locally without creating a GitHub repo
- `--skip-push`: create repo and commit, but don’t push

### Spec format (minimal)

The parser supports YAML frontmatter (recommended). Example:

```markdown
---
repo_name: example-api
description: Example generated API
template: fastapi-api
github:
  owner: your-org-or-user
  private: true
---

# Anything else
```

### Template system

Templates live under `templates/<template_name>/`. The renderer:

- Walks files in **sorted** order (deterministic)
- Copies files verbatim
- Optionally renders Jinja2 (`{{ ... }}`) in **text files** only

See `templates/fastapi-api/` for a minimal example template.


