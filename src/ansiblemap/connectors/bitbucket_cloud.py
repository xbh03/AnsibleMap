from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .common import RepositoryFile, RepositoryRef, YAML_EXTENSIONS


class BitbucketCloudConnector:
    provider_name = "bitbucket-cloud"

    def __init__(
        self,
        *,
        base_url: str,
        workspace: str,
        username: str | None,
        app_password: str | None,
        token: str | None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.workspace = workspace
        headers = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None

        if username and app_password:
            auth = (username, app_password)
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            raise ValueError(
                "For cloud, provide BITBUCKET_USERNAME/BITBUCKET_APP_PASSWORD or BITBUCKET_TOKEN"
            )

        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
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
        project_filter = set(project_keys or [])
        repos: list[RepositoryRef] = []

        if repo_slugs:
            for slug in repo_slugs:
                payload = self._get_json(f"/repositories/{self.workspace}/{slug}")
                repo = self._repo_from_payload(payload)
                if not project_filter or repo.project_key in project_filter:
                    repos.append(repo)
            return repos

        next_url = f"/repositories/{self.workspace}?pagelen=100"
        while next_url:
            payload = self._get_json(next_url)
            values = payload.get("values", [])
            for item in values:
                repo = self._repo_from_payload(item)
                if not project_filter or repo.project_key in project_filter:
                    repos.append(repo)
            next_url = payload.get("next")

        return repos

    def search_files(
        self,
        repo: RepositoryRef,
        query: str | None = None,
        max_files: int | None = None,
        max_file_size_bytes: int | None = None,
    ) -> Iterator[RepositoryFile]:
        collected = 0
        for path in self._list_tree(repo.slug, repo.default_branch):
            if not path.endswith(YAML_EXTENSIONS):
                continue

            if query and query not in path:
                continue

            content = self._download_file(
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get_json(self, path_or_url: str) -> dict[str, Any]:
        response = self.client.get(path_or_url)
        response.raise_for_status()
        return response.json()

    def _repo_from_payload(self, payload: dict[str, Any]) -> RepositoryRef:
        main_branch = payload.get("mainbranch") or {}
        project = payload.get("project") or {}
        return RepositoryRef(
            external_id=str(payload.get("uuid", payload.get("full_name", payload.get("slug", "unknown")))),
            slug=str(payload.get("slug")),
            default_branch=str(main_branch.get("name", "main")),
            project_key=str(project.get("key")) if project.get("key") else None,
        )

    def _list_tree(self, repo_slug: str, branch: str) -> list[str]:
        path = f"/repositories/{self.workspace}/{repo_slug}/src/{branch}/?pagelen=100"
        result: list[str] = []

        while path:
            payload = self._get_json(path)
            for item in payload.get("values", []):
                if item.get("type") != "commit_file":
                    continue
                file_path = item.get("path")
                if isinstance(file_path, str):
                    result.append(file_path)

            path = payload.get("next")

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _download_file(
        self,
        repo_slug: str,
        branch: str,
        path: str,
        *,
        max_file_size_bytes: int | None,
    ) -> str | None:
        with self.client.stream("GET", f"/repositories/{self.workspace}/{repo_slug}/src/{branch}/{path}") as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total_size = 0
            for chunk in response.iter_bytes():
                total_size += len(chunk)
                if max_file_size_bytes is not None and total_size > max_file_size_bytes:
                    return None
                chunks.append(chunk)

        return b"".join(chunks).decode("utf-8", errors="replace")
