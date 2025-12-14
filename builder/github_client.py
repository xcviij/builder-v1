"""
github_client.py

Responsibility: Isolate all direct GitHub REST API interaction.

This module must be the only place that:
- Constructs GitHub REST endpoints
- Sends HTTP requests to api.github.com
- Interprets GitHub API responses / error payloads

Everything else (rendering, git commands, CLI behavior) should use this client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    name: str
    html_url: str
    clone_url: str
    default_branch: str


class GitHubClient:
    def __init__(self, token: str, api_base: str = "https://api.github.com") -> None:
        if not token.strip():
            raise GitHubError("GitHub token is required.")
        self._token = token
        self._api_base = api_base.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "builder-v1",
        }

    def _request(self, method: str, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        url = f"{self._api_base}{path}"
        r = requests.request(method, url, headers=self._headers(), json=json_body, timeout=30)
        if r.status_code >= 400:
            try:
                payload = r.json()
            except Exception:
                payload = {"message": r.text}
            raise GitHubError(f"GitHub API error {r.status_code} {method} {path}: {payload.get('message', payload)}")
        if r.status_code == 204:
            return None
        return r.json()

    def get_repo(self, owner: str, name: str) -> RepoInfo | None:
        """
        Return RepoInfo if the repo exists and is accessible; otherwise None.
        """
        try:
            data = self._request("GET", f"/repos/{owner}/{name}")
        except GitHubError as e:
            # Best-effort: treat 404-like messages as missing.
            msg = str(e).lower()
            if "404" in msg or "not found" in msg:
                return None
            raise
        return RepoInfo(
            owner=owner,
            name=name,
            html_url=data["html_url"],
            clone_url=data["clone_url"],
            default_branch=data.get("default_branch") or "main",
        )

    def create_repo(
        self,
        *,
        owner: str,
        name: str,
        private: bool,
        description: str = "",
    ) -> RepoInfo:
        """
        Create a new repository under either:
        - the authenticated user (if owner matches the viewer login), OR
        - an organization (if owner is an org).

        This method uses the GitHub REST API only; git operations are handled elsewhere.
        """
        viewer = self._request("GET", "/user")
        viewer_login = str(viewer.get("login") or "")

        body = {
            "name": name,
            "private": private,
            "description": description,
            "auto_init": False,
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False,
        }

        if owner == viewer_login:
            data = self._request("POST", "/user/repos", json_body=body)
        else:
            data = self._request("POST", f"/orgs/{owner}/repos", json_body=body)

        return RepoInfo(
            owner=owner,
            name=name,
            html_url=data["html_url"],
            clone_url=data["clone_url"],
            default_branch=data.get("default_branch") or "main",
        )


