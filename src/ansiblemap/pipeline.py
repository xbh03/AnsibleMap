from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.orm import Session

from .db import (
    build_engine,
    ensure_schema_initialized,
    finalize_scan_run,
    insert_scan_run,
    replace_dependencies,
    upsert_artifacts,
    upsert_repository,
)
from .parsers.ansible_parser import ArtifactProjectScope, parse_repository_files


@dataclass(slots=True)
class PipelineSummary:
    repositories_processed: int
    artifacts_upserted: int
    dependencies_upserted: int


@dataclass(slots=True)
class ProjectSelection:
    playbooks: str | None
    roles: str | None
    collections: str | None


@dataclass(slots=True)
class ScanLimits:
    max_files_per_repo: int
    max_file_size_bytes: int


def run_bitbucket_scan(
    *,
    connector,
    database_url: str,
    repo_slugs: list[str] | None,
    file_query: str | None,
    projects: ProjectSelection,
    limits: ScanLimits,
) -> PipelineSummary:
    engine = build_engine(database_url)
    ensure_schema_initialized(engine)

    repositories_processed = 0
    artifacts_upserted = 0
    dependencies_upserted = 0

    with Session(engine) as session:
        scan_run = insert_scan_run(session, provider="bitbucket")
        session.commit()

        try:
            selected_projects = [p for p in {projects.playbooks, projects.roles, projects.collections} if p]
            project_keys = selected_projects or None
            repositories = connector.list_repositories(repo_slugs=repo_slugs, project_keys=project_keys)

            scope = ArtifactProjectScope(
                playbook_project_key=projects.playbooks,
                role_project_key=projects.roles,
                collection_project_key=projects.collections,
            )

            for repo in repositories:
                allowed_types = allowed_types_for_repo(repo.project_key, projects)
                if allowed_types is not None and not allowed_types:
                    continue

                repository_row = upsert_repository(
                    session,
                    provider=connector.provider_name,
                    external_id=repo.external_id,
                    slug=repo.slug,
                    default_branch=repo.default_branch,
                )

                repo_files = connector.search_files(
                    repo,
                    query=file_query,
                    max_files=limits.max_files_per_repo,
                    max_file_size_bytes=limits.max_file_size_bytes,
                )
                parsed = parse_repository_files(
                    repo.slug,
                    repo.project_key,
                    repo_files,
                    scope,
                    allowed_types=allowed_types,
                )

                artifacts_map = upsert_artifacts(session, repository_row.id, parsed.artifacts)
                deps_count = replace_dependencies(session, artifacts_map, parsed.dependencies)

                repositories_processed += 1
                artifacts_upserted += len(parsed.artifacts)
                dependencies_upserted += deps_count
                session.commit()

            finalize_scan_run(session, scan_run.id, status="success")
            session.commit()

        except Exception as exc:
            finalize_scan_run(session, scan_run.id, status="failed", error_message=str(exc))
            session.commit()
            raise

    return PipelineSummary(
        repositories_processed=repositories_processed,
        artifacts_upserted=artifacts_upserted,
        dependencies_upserted=dependencies_upserted,
    )


def allowed_types_for_repo(repo_project_key: str | None, projects: ProjectSelection) -> set[str] | None:
    project_values = [projects.playbooks, projects.roles, projects.collections]
    if not any(project_values):
        return None

    allowed: set[str] = set()
    if projects.playbooks and projects.playbooks == repo_project_key:
        allowed.add("playbook")
    if projects.roles and projects.roles == repo_project_key:
        allowed.add("role")
    if projects.collections and projects.collections == repo_project_key:
        allowed.add("collection")

    return allowed
