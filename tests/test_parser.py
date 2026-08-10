from __future__ import annotations

import sys
import unittest

if sys.version_info < (3, 11):
    raise unittest.SkipTest("Tests require Python 3.11+")

from ansiblemap.connectors.common import RepositoryFile
from ansiblemap.parsers.ansible_parser import ArtifactProjectScope, parse_repository_files


class ParserTests(unittest.TestCase):
    def test_extracts_playbook_role_and_collection_dependencies(self) -> None:
        files = [
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
        ]

        parsed = parse_repository_files(
            repo_slug="repo-aip",
            repo_project_key="PRJ_PLAYBOOK",
            files=files,
            project_scope=ArtifactProjectScope(
                playbook_project_key="PRJ_PLAYBOOK",
                role_project_key="PRJ_ROLE",
                collection_project_key="PRJ_COLLECTION",
            ),
        )

        self.assertEqual(len(parsed.artifacts), 1)
        dep_types = {d.dep_type for d in parsed.dependencies}
        targets = {d.to_external_key for d in parsed.dependencies}

        self.assertIn("uses_role", dep_types)
        self.assertIn("uses_collection", dep_types)
        self.assertIn("role:PRJ_ROLE:hello_role", targets)
        self.assertIn("collection:PRJ_COLLECTION:demo.hello_collection", targets)


if __name__ == "__main__":
    unittest.main()
