from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy.exc import SQLAlchemyError
import typer

from .config import Settings
from .connectors.bitbucket_cloud import BitbucketCloudConnector
from .connectors.bitbucket_datacenter import BitbucketDataCenterConnector
from .db import build_engine, create_schema
from .db import SchemaNotInitializedError
from .pipeline import ProjectSelection, ScanLimits, run_bitbucket_scan

app = typer.Typer(help="AnsibleMap")


@app.command("init-db")
def init_db() -> None:
    """Initialize database schema explicitly before running scans."""
    settings = Settings.from_env()
    engine = build_engine(settings.database_url)

    if engine.dialect.name == "postgresql":
        migration_path = Path("sql/migrations/0001_init.sql")
        if not migration_path.exists():
            raise typer.BadParameter(f"Migration file not found: {migration_path}")

        sql_script = migration_path.read_text(encoding="utf-8")
        statements = [stmt.strip() for stmt in sql_script.split(";") if stmt.strip()]

        with engine.begin() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)

        typer.echo("Database schema initialized from SQL migration: sql/migrations/0001_init.sql")
        return

    # Local fallback (e.g., SQLite demo): keep ORM create for non-Postgres engines.
    create_schema(engine)
    typer.echo("Database schema initialized with ORM fallback (non-PostgreSQL engine)")


@app.command("scan-bitbucket")
def scan_bitbucket(
    repos: Optional[str] = typer.Option(
        default=None,
        help="Comma-separated repository slugs. If omitted, scans all repos in selected projects.",
    ),
    file_query: Optional[str] = typer.Option(
        default=None,
        help="Optional path substring to filter candidate YAML files.",
    ),
    deployment: Optional[str] = typer.Option(
        default=None,
        help="Bitbucket mode: cloud or datacenter. Overrides BITBUCKET_DEPLOYMENT.",
    ),
    project_playbooks: Optional[str] = typer.Option(
        default=None,
        help="Project key that contains playbook repositories.",
    ),
    project_roles: Optional[str] = typer.Option(
        default=None,
        help="Project key that contains role repositories.",
    ),
    project_collections: Optional[str] = typer.Option(
        default=None,
        help="Project key that contains collection repositories.",
    ),
) -> None:
    settings = Settings.from_env()
    effective_deployment = (deployment or settings.bitbucket_deployment).strip().lower()
    if effective_deployment not in {"cloud", "datacenter"}:
        raise typer.BadParameter("Deployment must be 'cloud' or 'datacenter'")

    repo_slugs = [r.strip() for r in repos.split(",") if r.strip()] if repos else None

    scope = ProjectSelection(
        playbooks=project_playbooks or settings.project_playbooks,
        roles=project_roles or settings.project_roles,
        collections=project_collections or settings.project_collections,
    )
    limits = ScanLimits(
        max_files_per_repo=settings.max_files_per_repo,
        max_file_size_bytes=settings.max_file_size_bytes,
    )

    if effective_deployment == "cloud":
        if not settings.bitbucket_workspace:
            raise typer.BadParameter("BITBUCKET_WORKSPACE is required for cloud")
        # Primary auth path: app password (works on Free plan); token is optional fallback.
        if (not settings.bitbucket_username or not settings.bitbucket_app_password) and not settings.bitbucket_token:
            raise typer.BadParameter(
                "For cloud, provide BITBUCKET_USERNAME+BITBUCKET_APP_PASSWORD (recommended) or BITBUCKET_TOKEN"
            )
        connector = BitbucketCloudConnector(
            base_url=settings.bitbucket_base_url,
            workspace=settings.bitbucket_workspace,
            username=settings.bitbucket_username,
            app_password=settings.bitbucket_app_password,
            token=settings.bitbucket_token,
            timeout_seconds=settings.request_timeout_seconds,
        )
    else:
        connector = BitbucketDataCenterConnector(
            base_url=settings.bitbucket_base_url,
            username=settings.bitbucket_username,
            password=settings.bitbucket_password or settings.bitbucket_app_password,
            token=settings.bitbucket_token,
            timeout_seconds=settings.request_timeout_seconds,
        )

    try:
        summary = run_bitbucket_scan(
            connector=connector,
            database_url=settings.database_url,
            repo_slugs=repo_slugs,
            file_query=file_query,
            projects=scope,
            limits=limits,
        )
    except SchemaNotInitializedError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        typer.echo(
            f"Bitbucket API error (HTTP {status_code}). Verify credentials, permissions, and workspace/project access.",
            err=True,
        )
        raise typer.Exit(code=3)
    except httpx.HTTPError as exc:
        typer.echo(f"Network/API error while contacting Bitbucket: {exc}", err=True)
        raise typer.Exit(code=3)
    except SQLAlchemyError as exc:
        typer.echo(f"Database error during scan: {exc}", err=True)
        raise typer.Exit(code=4)
    except Exception as exc:
        typer.echo(f"Unexpected scan error: {exc}", err=True)
        raise typer.Exit(code=1)
    finally:
        connector.close()

    typer.echo(
        "Scan completed: "
        f"repositories={summary.repositories_processed}, "
        f"artifacts={summary.artifacts_upserted}, "
        f"dependencies={summary.dependencies_upserted}"
    )


if __name__ == "__main__":
    app()
