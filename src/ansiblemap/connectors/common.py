from __future__ import annotations

from dataclasses import dataclass


YAML_EXTENSIONS = (".yml", ".yaml")


@dataclass(slots=True)
class RepositoryRef:
    external_id: str
    slug: str
    default_branch: str
    project_key: str | None


@dataclass(slots=True)
class RepositoryFile:
    path: str
    content: str
