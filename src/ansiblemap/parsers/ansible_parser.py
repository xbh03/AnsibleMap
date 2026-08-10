from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath
from typing import Any, Iterable

import yaml

from ..connectors.common import RepositoryFile
from ..types import ArtifactInput, DependencyInput, ScanResult


ROLE_IMPORT_KEYS = {"import_role", "include_role"}
PLAYBOOK_IMPORT_KEYS = {"import_playbook"}
TASK_COLLECTION_KEYS = {"ansible.builtin.include_tasks", "include_tasks", "import_tasks"}


@dataclass(slots=True)
class ArtifactProjectScope:
    playbook_project_key: str | None
    role_project_key: str | None
    collection_project_key: str | None


def parse_repository_files(
    repo_slug: str,
    repo_project_key: str | None,
    files: Iterable[RepositoryFile],
    project_scope: ArtifactProjectScope,
    allowed_types: set[str] | None = None,
) -> ScanResult:
    artifacts: list[ArtifactInput] = []
    dependencies: list[DependencyInput] = []

    for f in files:
        parsed = safe_yaml_load(f.content)
        if parsed is None:
            continue

        artifact = identify_artifact(repo_slug, repo_project_key, f.path, f.content, parsed, project_scope)
        if artifact is None:
            continue
        if allowed_types is not None and artifact.type not in allowed_types:
            continue

        artifacts.append(artifact)
        dependencies.extend(extract_dependencies(repo_slug, repo_project_key, artifact, parsed, project_scope))

    return ScanResult(artifacts=artifacts, dependencies=dependencies)


def safe_yaml_load(content: str) -> Any | None:
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return None


def identify_artifact(
    repo_slug: str,
    repo_project_key: str | None,
    path: str,
    content: str,
    parsed: Any,
    project_scope: ArtifactProjectScope,
) -> ArtifactInput | None:
    p = PurePosixPath(path)
    fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
    playbook_project = project_scope.playbook_project_key or repo_project_key or "default"
    role_project = project_scope.role_project_key or repo_project_key or "default"
    collection_project = project_scope.collection_project_key or repo_project_key or "default"

    if p.name == "galaxy.yml" and isinstance(parsed, dict):
        name = f"{parsed.get('namespace', 'unknown')}.{parsed.get('name', p.parent.name)}"
        return ArtifactInput(
            external_key=f"collection:{collection_project}:{name}",
            type="collection",
            name=name,
            path=path,
            fingerprint=fingerprint,
            metadata={"manifest": parsed},
        )

    if "roles" in p.parts and p.name in {"main.yml", "main.yaml"}:
        role_name = detect_role_name(p)
        return ArtifactInput(
            external_key=f"role:{role_project}:{role_name}",
            type="role",
            name=role_name,
            path=path,
            fingerprint=fingerprint,
            metadata={"source": "role-meta-or-task", "raw_path": path},
        )

    if is_probable_playbook_path(p) and isinstance(parsed, list):
        playbook_name = p.stem
        return ArtifactInput(
            external_key=f"playbook:{playbook_project}:{repo_slug}:{path}",
            type="playbook",
            name=playbook_name,
            path=path,
            fingerprint=fingerprint,
            metadata={"plays_count": len(parsed)},
        )

    return None


def detect_role_name(path: PurePosixPath) -> str:
    parts = list(path.parts)
    if "roles" in parts:
        roles_idx = parts.index("roles")
        if roles_idx + 1 < len(parts):
            return parts[roles_idx + 1]
    return path.parent.parent.name


def is_probable_playbook_path(path: PurePosixPath) -> bool:
    if path.suffix not in {".yml", ".yaml"}:
        return False

    blacklist = {"defaults", "vars", "handlers", "tasks", "meta", "group_vars", "host_vars"}
    if any(part in blacklist for part in path.parts):
        return False

    return True


def extract_dependencies(
    repo_slug: str,
    repo_project_key: str | None,
    artifact: ArtifactInput,
    parsed: Any,
    project_scope: ArtifactProjectScope,
) -> list[DependencyInput]:
    deps: list[DependencyInput] = []
    role_project = project_scope.role_project_key or repo_project_key or "default"
    collection_project = project_scope.collection_project_key or repo_project_key or "default"
    playbook_project = project_scope.playbook_project_key or repo_project_key or "default"

    if artifact.type == "playbook" and isinstance(parsed, list):
        for play in parsed:
            if not isinstance(play, dict):
                continue

            collections = play.get("collections", [])
            for collection_name in normalize_collections_list(collections):
                deps.append(
                    DependencyInput(
                        from_external_key=artifact.external_key,
                        to_external_key=f"collection:{collection_project}:{collection_name}",
                        dep_type="uses_collection",
                    )
                )

            roles = play.get("roles", [])
            for role in normalize_roles_list(roles):
                deps.append(
                    DependencyInput(
                        from_external_key=artifact.external_key,
                        to_external_key=f"role:{role_project}:{role}",
                        dep_type="uses_role",
                    )
                )

            deps.extend(
                extract_nested_task_deps(
                    repo_slug,
                    artifact.external_key,
                    play,
                    role_project,
                    playbook_project,
                )
            )

    if artifact.type == "role" and isinstance(parsed, dict):
        role_meta_deps = parsed.get("dependencies", [])
        for role in normalize_roles_list(role_meta_deps):
            deps.append(
                DependencyInput(
                    from_external_key=artifact.external_key,
                    to_external_key=f"role:{role_project}:{role}",
                    dep_type="depends_on_role",
                )
            )

    if artifact.type == "collection":
        manifest = artifact.metadata.get("manifest", {})
        dependencies_map = manifest.get("dependencies", {}) if isinstance(manifest, dict) else {}
        if isinstance(dependencies_map, dict):
            for collection_name in dependencies_map.keys():
                deps.append(
                    DependencyInput(
                        from_external_key=artifact.external_key,
                        to_external_key=f"collection:{collection_project}:{collection_name}",
                        dep_type="depends_on_collection",
                    )
                )

    return deps


def normalize_roles_list(roles: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(roles, list):
        return result

    for role_entry in roles:
        if isinstance(role_entry, str):
            result.append(role_entry)
        elif isinstance(role_entry, dict):
            role_name = role_entry.get("role")
            if isinstance(role_name, str):
                result.append(role_name)

    return result


def normalize_collections_list(collections: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(collections, list):
        return result

    for item in collections:
        if isinstance(item, str):
            result.append(item)

    return result


def extract_nested_task_deps(
    repo_slug: str,
    from_external_key: str,
    data: Any,
    role_project: str,
    playbook_project: str,
) -> list[DependencyInput]:
    deps: list[DependencyInput] = []

    if isinstance(data, dict):
        for key, value in data.items():
            if key in ROLE_IMPORT_KEYS and isinstance(value, dict):
                role_name = value.get("name")
                if isinstance(role_name, str):
                    deps.append(
                        DependencyInput(
                            from_external_key=from_external_key,
                            to_external_key=f"role:{role_project}:{role_name}",
                            dep_type="imports_role",
                        )
                    )

            if key in PLAYBOOK_IMPORT_KEYS and isinstance(value, str):
                deps.append(
                    DependencyInput(
                        from_external_key=from_external_key,
                        to_external_key=f"playbook:{playbook_project}:{repo_slug}:{value}",
                        dep_type="imports_playbook",
                    )
                )

            if key in TASK_COLLECTION_KEYS and isinstance(value, str):
                deps.append(
                    DependencyInput(
                        from_external_key=from_external_key,
                        to_external_key=f"taskfile:{repo_slug}:{value}",
                        dep_type="includes_task_file",
                    )
                )

            deps.extend(extract_nested_task_deps(repo_slug, from_external_key, value, role_project, playbook_project))

    elif isinstance(data, list):
        for item in data:
            deps.extend(extract_nested_task_deps(repo_slug, from_external_key, item, role_project, playbook_project))

    return deps
