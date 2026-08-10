from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .common import RepositoryFile, RepositoryRef, YAML_EXTENSIONS


class BitbucketDataCenterConnector:
    provider_name = "bitbucket-datacenter"

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None,
        password: str | None,
        token: str | None,
        timeout_seconds: float = 30.0,
    ) -> None:
        api_base = base_url.rstrip("/")
        if not api_base.endswith("/rest/api/1.0"):
            api_base = f"{api_base}/rest/api/1.0"

        headers = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None

        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            auth = (username, password)
        else:
            raise ValueError("For Data Center provide BITBUCKET_TOKEN or BITBUCKET_USERNAME/BITBUCKET_PASSWORD")

        self.client = httpx.Client(
            base_url=api_base,
            auth=auth,
            timeout=timeout_seconds,
            headers=headers,
        )

    def close(self) -> None:
        self.client.close()

    def list_repositories(
        self,
        repo_slugs: list[str] | None = None,
        project_keys: list[str] | None = None,
    ) -> list[RepositoryRef]:
        repos: list[RepositoryRef] = []

        if repo_slugs and not project_keys:
            raise ValueError("For Bitbucket Data Center, repo slugs require project keys")

        effective_projects = project_keys or self._list_projects()

        for project_key in effective_projects:
            if repo_slugs:
                for slug in repo_slugs:
                    payload = self._get_json(f"/projects/{project_key}/repos/{slug}")
                    repos.append(self._repo_from_payload(payload, project_key))
                continue

            next_start = 0
            is_last_page = False
            while not is_last_page:
                payload = self._get_json(f"/projects/{project_key}/repos?limit=100&start={next_start}")
                for item in payload.get("values", []):
                    repos.append(self._repo_from_payload(item, project_key))

                is_last_page = bool(payload.get("isLastPage", True))
                next_start = int(payload.get("nextPageStart", 0))

        return repos

    def search_files(
        self,
        repo: RepositoryRef,
        query: str | None = None,
        max_files: int | None = None,
        max_file_size_bytes: int | None = None,
    ) -> Iterator[RepositoryFile]:
        if not repo.project_key:
            raise ValueError("Repository project key is required for Data Center file listing")

        collected = 0
        for path in self._list_tree(repo.project_key, repo.slug, repo.default_branch):
            if not path.endswith(YAML_EXTENSIONS):
                continue

            if query and query not in path:
                continue

            content = self._download_file(
                repo.project_key,
                repo.slug,
                repo.default_branch,
                path,
                max_file_size_bytes=max_file_size_bytes,
            )
            if content is None:
                continue

            yield RepositoryFile(path=path, content=content)
            collected += 1
            if max_files is not None and collected >= max_files:
                break

    def _list_projects(self) -> list[str]:
        projects: list[str] = []
        next_start = 0
        is_last_page = False

        while not is_last_page:
            payload = self._get_json(f"/projects?limit=100&start={next_start}")
            for item in payload.get("values", []):
                key = item.get("key")
                if isinstance(key, str):
                    projects.append(key)

            is_last_page = bool(payload.get("isLastPage", True))
            next_start = int(payload.get("nextPageStart", 0))

        return projects

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get_json(self, path: str) -> dict[str, Any]:
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def _repo_from_payload(self, payload: dict[str, Any], fallback_project_key: str) -> RepositoryRef:
        project = payload.get("project") or {}
        default_branch = payload.get("defaultBranch") or {}
        project_key = project.get("key", fallback_project_key)
        return RepositoryRef(
            external_id=f"{project_key}:{payload.get('slug', 'unknown')}",
            slug=str(payload.get("slug")),
            default_branch=str(default_branch.get("displayId", "main")),
            project_key=str(project_key),
        )

    def _list_tree(self, project_key: str, repo_slug: str, branch: str) -> list[str]:
        result: list[str] = []
        next_start = 0
        is_last_page = False

        while not is_last_page:
            payload = self._get_json(
                f"/projects/{project_key}/repos/{repo_slug}/files?at=refs/heads/{branch}&limit=1000&start={next_start}"
            )
            for file_path in payload.get("values", []):
                if isinstance(file_path, str):
                    result.append(file_path)

            is_last_page = bool(payload.get("isLastPage", True))
            next_start = int(payload.get("nextPageStart", 0))

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _download_file(
        self,
        project_key: str,
        repo_slug: str,
        branch: str,
        path: str,
        *,
        max_file_size_bytes: int | None,
    ) -> str | None:
        with self.client.stream(
            "GET",
            f"/projects/{project_key}/repos/{repo_slug}/raw/{path}",
            params={"at": f"refs/heads/{branch}"},
        ) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total_size = 0
            for chunk in response.iter_bytes():
                total_size += len(chunk)
                if max_file_size_bytes is not None and total_size > max_file_size_bytes:
                    return None
                chunks.append(chunk)

        return b"".join(chunks).decode("utf-8", errors="replace")
