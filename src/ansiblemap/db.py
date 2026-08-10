from __future__ import annotations

from datetime import datetime
import json
from typing import Iterable

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from .types import ArtifactInput, DependencyInput


class Base(DeclarativeBase):
    pass


class SchemaNotInitializedError(RuntimeError):
    pass


REQUIRED_TABLES = ("scan_run", "repository", "artifact", "dependency")


class ScanRun(Base):
    __tablename__ = "scan_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Repository(Base):
    __tablename__ = "repository"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_repository_provider_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)

    artifacts: Mapped[list[Artifact]] = relationship(back_populates="repository")


class Artifact(Base):
    __tablename__ = "artifact"
    __table_args__ = (UniqueConstraint("repo_id", "external_key", name="uq_artifact_repo_external_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repository.id"), nullable=False)
    external_key: Mapped[str] = mapped_column(String(600), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    repository: Mapped[Repository] = relationship(back_populates="artifacts")


class Dependency(Base):
    __tablename__ = "dependency"
    __table_args__ = (UniqueConstraint("from_artifact_id", "to_artifact_id", "dep_type", name="uq_dependency_edge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_artifact_id: Mapped[int] = mapped_column(ForeignKey("artifact.id"), nullable=False)
    to_artifact_id: Mapped[int] = mapped_column(ForeignKey("artifact.id"), nullable=False)
    dep_type: Mapped[str] = mapped_column(String(50), nullable=False)


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url, future=True)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def missing_required_tables(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    return [table for table in REQUIRED_TABLES if table not in existing]


def ensure_schema_initialized(engine: Engine) -> None:
    missing = missing_required_tables(engine)
    if missing:
        missing_csv = ", ".join(missing)
        raise SchemaNotInitializedError(
            "Database schema is not initialized. "
            f"Missing tables: {missing_csv}. "
            "Run 'PYTHONPATH=src python -m ansiblemap.cli init-db' first."
        )


def insert_scan_run(session: Session, provider: str) -> ScanRun:
    run = ScanRun(provider=provider, started_at=datetime.utcnow(), finished_at=None, status="running", error_message=None)
    session.add(run)
    session.flush()
    return run


def finalize_scan_run(session: Session, run_id: int, status: str, error_message: str | None = None) -> None:
    run = session.get(ScanRun, run_id)
    if run is None:
        return
    run.finished_at = datetime.utcnow()
    run.status = status
    run.error_message = error_message


def upsert_repository(session: Session, *, provider: str, external_id: str, slug: str, default_branch: str) -> Repository:
    stmt = select(Repository).where(Repository.provider == provider, Repository.external_id == external_id)
    repo = session.scalar(stmt)
    if repo is None:
        repo = Repository(provider=provider, external_id=external_id, slug=slug, default_branch=default_branch)
        session.add(repo)
        session.flush()
        return repo

    repo.slug = slug
    repo.default_branch = default_branch
    return repo


def upsert_artifacts(
    session: Session,
    repo_id: int,
    artifacts: Iterable[ArtifactInput],
) -> dict[str, Artifact]:
    by_external_key: dict[str, Artifact] = {}

    for artifact_in in artifacts:
        stmt = select(Artifact).where(Artifact.repo_id == repo_id, Artifact.external_key == artifact_in.external_key)
        existing = session.scalar(stmt)
        if existing is None:
            existing = Artifact(
                repo_id=repo_id,
                external_key=artifact_in.external_key,
                type=artifact_in.type,
                name=artifact_in.name,
                path=artifact_in.path,
                fingerprint=artifact_in.fingerprint,
                metadata_json=artifact_in.metadata,
            )
            session.add(existing)
            session.flush()
        else:
            existing.type = artifact_in.type
            existing.name = artifact_in.name
            existing.path = artifact_in.path
            existing.fingerprint = artifact_in.fingerprint
            existing.metadata_json = artifact_in.metadata

        by_external_key[artifact_in.external_key] = existing

    return by_external_key


def replace_dependencies(
    session: Session,
    artifacts_map: dict[str, Artifact],
    dependencies: Iterable[DependencyInput],
) -> int:
    artifact_ids = [a.id for a in artifacts_map.values()]
    if artifact_ids:
        session.query(Dependency).filter(Dependency.from_artifact_id.in_(artifact_ids)).delete(synchronize_session=False)

    created = 0
    for dep in dependencies:
        from_artifact = artifacts_map.get(dep.from_external_key)
        to_artifact = session.scalar(select(Artifact).where(Artifact.external_key == dep.to_external_key).limit(1))
        if from_artifact is None or to_artifact is None:
            continue

        session.add(
            Dependency(
                from_artifact_id=from_artifact.id,
                to_artifact_id=to_artifact.id,
                dep_type=dep.dep_type,
            )
        )
        created += 1

    return created


def artifact_metadata_to_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=True)
