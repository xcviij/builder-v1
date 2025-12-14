"""
cli.py

Responsibility: CLI entrypoint for Builder v1.

High-level flow (single command `build`):
1) Parse spec markdown -> `Spec`
2) Render template -> local workdir
3) (Optional) Create GitHub repo via GitHub REST API
4) Initialize git, commit, push to `main`

This module should orchestrate behavior but keep concerns isolated:
- Spec parsing: `spec_parser.py`
- Rendering: `renderer.py`
- GitHub API: `github_client.py`
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from builder.github_client import GitHubClient
from builder.renderer import render_template_dir
from builder.spec_parser import Spec, parse_spec


class CLIError(RuntimeError):
    pass


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    """
    Run a subprocess command, raising a CLIError on failure.
    """
    try:
        subprocess.run(cmd, cwd=str(cwd), env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        raise CLIError(f"Command failed: {' '.join(cmd)}\n\n{e.stdout}") from e


def _git_env_deterministic(base_env: dict[str, str]) -> dict[str, str]:
    """
    Deterministic git commit metadata to reduce non-determinism in generated repos.
    (The rendered file contents are already deterministic.)
    """
    env = dict(base_env)
    env.setdefault("GIT_AUTHOR_NAME", "builder-v1")
    env.setdefault("GIT_AUTHOR_EMAIL", "builder-v1@example.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "builder-v1")
    env.setdefault("GIT_COMMITTER_EMAIL", "builder-v1@example.invalid")
    env.setdefault("GIT_AUTHOR_DATE", "1970-01-01T00:00:00Z")
    env.setdefault("GIT_COMMITTER_DATE", "1970-01-01T00:00:00Z")
    return env


def _ensure_empty_dir(path: Path, *, overwrite: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        # If any children exist, refuse.
        if any(path.iterdir()):
            raise CLIError(f"Workdir is not empty: {path} (use --overwrite to allow)")


def _build_context(spec: Spec) -> dict[str, object]:
    # Deterministic keys; templates should reference these.
    return {
        "repo_name": spec.repo_name,
        "description": spec.description,
        "github_owner": spec.github.owner or "",
        "private": spec.github.private,
        "variables": spec.variables,
        **spec.variables,  # convenience access: {{ some_var }}
    }


def _git_init_commit_push(
    *,
    workdir: Path,
    remote_url: str | None,
    push: bool,
    deterministic_git: bool,
) -> None:
    base_env = os.environ.copy()
    env = _git_env_deterministic(base_env) if deterministic_git else base_env

    if not (workdir / ".git").exists():
        _run(["git", "init"], cwd=workdir, env=env)

    _run(["git", "checkout", "-B", "main"], cwd=workdir, env=env)
    _run(["git", "add", "-A"], cwd=workdir, env=env)
    _run(["git", "commit", "-m", "Initial commit"], cwd=workdir, env=env)

    if remote_url:
        _run(["git", "remote", "add", "origin", remote_url], cwd=workdir, env=env)

    if push and remote_url:
        _run(["git", "push", "-u", "origin", "main"], cwd=workdir, env=env)


def _tokenized_https_remote(clone_url: str, token: str) -> str:
    """
    Convert https://github.com/owner/name.git into an HTTPS URL containing a token.

    Note: this stores the token in `.git/config` once set as a remote. For production,
    prefer a credential helper or GIT_ASKPASS. This is a pragmatic placeholder.
    """
    # GitHub supports x-access-token in the username position.
    # Example: https://x-access-token:TOKEN@github.com/owner/name.git
    return clone_url.replace("https://", f"https://x-access-token:{token}@")


def build_cmd(args: argparse.Namespace) -> int:
    spec = parse_spec(args.spec_path)

    # CLI overrides
    template_name = args.template or spec.template
    github_owner = args.github_owner or spec.github.owner
    private = spec.github.private if args.private is None else bool(args.private)

    workdir = Path(args.workdir or Path("generated") / spec.repo_name).resolve()
    _ensure_empty_dir(workdir, overwrite=bool(args.overwrite))

    template_dir = Path(args.templates_dir).resolve() / template_name
    context = _build_context(
        Spec(
            repo_name=spec.repo_name,
            description=spec.description,
            template=template_name,
            github=spec.github.__class__(owner=github_owner, private=private),
            variables=spec.variables,
        )
    )

    render_template_dir(template_dir=template_dir, destination_dir=workdir, context=context)

    remote_url: str | None = None
    do_push = not bool(args.skip_push)

    if not bool(args.skip_github):
        if not github_owner:
            raise CLIError("--github-owner is required unless --skip-github is set")
        token = args.github_token or os.environ.get("GITHUB_TOKEN") or ""
        if not token:
            raise CLIError("GitHub token is required (use --github-token or set GITHUB_TOKEN)")
        gh = GitHubClient(token)

        existing = gh.get_repo(github_owner, spec.repo_name)
        if existing is None:
            repo = gh.create_repo(
                owner=github_owner,
                name=spec.repo_name,
                private=private,
                description=spec.description,
            )
        else:
            repo = existing

        remote_url = _tokenized_https_remote(repo.clone_url, token)

    _git_init_commit_push(
        workdir=workdir,
        remote_url=remote_url,
        push=do_push,
        deterministic_git=bool(args.deterministic_git),
    )

    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="builder-v1", description="Builder v1 - deterministic template-to-repo generator")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Render a template from a spec, create repo, commit, push")
    b.add_argument("spec_path", help="Path to the spec markdown file")
    b.add_argument("--templates-dir", default="templates", help="Templates directory (default: templates)")
    b.add_argument("--template", default=None, help="Template name (overrides spec.template)")
    b.add_argument("--workdir", default=None, help="Directory to render into and run git operations")
    b.add_argument("--overwrite", action="store_true", help="Allow non-empty workdir")

    b.add_argument("--skip-github", action="store_true", help="Do not create/lookup GitHub repo")
    b.add_argument("--skip-push", action="store_true", help="Do not push to GitHub (still commits locally)")

    b.add_argument("--github-owner", default=None, help="GitHub owner (user or org)")
    b.add_argument("--github-token", default=None, help="GitHub token (or set env GITHUB_TOKEN)")
    b.add_argument("--private", dest="private", action="store_true", default=None, help="Create a private repo")
    b.add_argument("--public", dest="private", action="store_false", default=None, help="Create a public repo")

    b.add_argument(
        "--deterministic-git",
        action="store_true",
        default=True,
        help="Use deterministic git author/commit timestamps (default: enabled)",
    )
    b.add_argument(
        "--no-deterministic-git",
        dest="deterministic_git",
        action="store_false",
        help="Disable deterministic git commit timestamps",
    )

    b.set_defaults(func=build_cmd)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())


