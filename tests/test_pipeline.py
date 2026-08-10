from __future__ import annotations

import sys
import tempfile
import unittest

if sys.version_info < (3, 11):
    raise unittest.SkipTest("Tests require Python 3.11+")

from sqlalchemy import text
from sqlalchemy.orm import Session

from ansiblemap.connectors.common import RepositoryFile, RepositoryRef
from ansiblemap.db import SchemaNotInitializedError, build_engine, create_schema
from ansiblemap.pipeline import ProjectSelection, ScanLimits, run_bitbucket_scan


class FakeConnector:
    provider_name = "demo-local"

    def list_repositories(self, repo_slugs=None, project_keys=None):
        repos = [
            RepositoryRef(external_id="PRJ_ROLE:r", slug="r", default_branch="main", project_key="PRJ_ROLE"),
            RepositoryRef(
                external_id="PRJ_COLLECTION:c",
                slug="c",
                default_branch="main",
                project_key="PRJ_COLLECTION",
            ),
            RepositoryRef(
                external_id="PRJ_PLAYBOOK:p",
                slug="p",
                default_branch="main",
                project_key="PRJ_PLAYBOOK",
            ),
        ]
        if project_keys:
            allowed = set(project_keys)
            repos = [r for r in repos if r.project_key in allowed]
        return repos

    def search_files(self, repo, query=None, max_files=None, max_file_size_bytes=None):
        data = {
            "r": [RepositoryFile(path="roles/hello_role/tasks/main.yml", content="- debug: msg='x'")],
            "c": [RepositoryFile(path="galaxy.yml", content="namespace: demo\nname: hello_collection\nversion: 1.0.0")],
            "p": [
                RepositoryFile(
                    path="hello.yml",
                    content="""---
- hosts: localhost
  gather_facts: false
  collections:
    - demo.hello_collection
  roles:
    - hello_role
""",
                )
            ],
        }
        emitted = 0
        for item in data.get(repo.slug, []):
            if query and query not in item.path:
                continue
            if max_file_size_bytes is not None and len(item.content.encode("utf-8")) > max_file_size_bytes:
                continue
            yield item
            emitted += 1
            if max_files is not None and emitted >= max_files:
                break


class PipelineTests(unittest.TestCase):
    def test_pipeline_fails_when_schema_not_initialized(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db_url = f"sqlite:///{tmp.name}"

            with self.assertRaises(SchemaNotInitializedError):
                run_bitbucket_scan(
                    connector=FakeConnector(),
                    database_url=db_url,
                    repo_slugs=None,
                    file_query=None,
                    projects=ProjectSelection(
                        playbooks="PRJ_PLAYBOOK",
                        roles="PRJ_ROLE",
                        collections="PRJ_COLLECTION",
                    ),
                    limits=ScanLimits(max_files_per_repo=100, max_file_size_bytes=1024 * 1024),
                )

    def test_pipeline_writes_artifacts_and_dependencies(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            db_url = f"sqlite:///{tmp.name}"
            engine = build_engine(db_url)
            create_schema(engine)

            summary = run_bitbucket_scan(
                connector=FakeConnector(),
                database_url=db_url,
                repo_slugs=None,
                file_query=None,
                projects=ProjectSelection(
                    playbooks="PRJ_PLAYBOOK",
                    roles="PRJ_ROLE",
                    collections="PRJ_COLLECTION",
                ),
                limits=ScanLimits(max_files_per_repo=100, max_file_size_bytes=1024 * 1024),
            )

            self.assertEqual(summary.repositories_processed, 3)
            self.assertEqual(summary.artifacts_upserted, 3)
            self.assertGreaterEqual(summary.dependencies_upserted, 2)

            with Session(engine) as session:
                repos = session.execute(text("select count(*) from repository")).scalar_one()
                artifacts = session.execute(text("select count(*) from artifact")).scalar_one()
                deps = session.execute(text("select count(*) from dependency")).scalar_one()

            self.assertEqual(repos, 3)
            self.assertEqual(artifacts, 3)
            self.assertGreaterEqual(deps, 2)


if __name__ == "__main__":
    unittest.main()
