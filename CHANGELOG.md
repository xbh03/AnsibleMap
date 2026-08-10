# Changelog

Short history of important updates.

## [0.2.5] - 2026-08-10

Quality and usability improvements.

- Added explicit pre-scan schema validation with clear missing-table errors.
- Added dedicated schema readiness exception to guide users to run DB initialization first.
- Improved CLI scan error handling with user-friendly messages for API/auth/network/database failures.
- Added pipeline test coverage for the schema-not-initialized guardrail.
- Updated README header with a GitHub-compatible logo embed.

## [0.2.4] - 2026-08-10

Release hardening update.

- Aligned package version metadata with changelog (`0.2.4`).
- Stopped automatic schema creation during scans; DB init is now explicit.
- Added initial SQL migration file: `sql/migrations/0001_init.sql`.
- Added test coverage for parser and pipeline core paths.
- Clarified Python support matrix and Cloud auth mode in documentation.
- Improved Cloud auth logic: app password is primary, token is fallback.

## [0.2.3] - 2026-08-10

Dependency compatibility fix.

- Updated `psycopg[binary]` from `3.2.1` to `3.2.13` in both project dependency files.

## [0.2.2] - 2026-08-10

Security and stability hardening.

- Added scan safety limits for max files per repository and max file size.
- Switched file downloads to streaming with size checks to reduce memory risk on large scans.
- Reduced in-memory duplication between connector output and parser input.
- Pinned Python dependencies to exact versions for reproducible builds.
- Updated docs and env example with new scan limit options.

## [0.2.1] - 2026-08-10

Small improvements and cleanup.

- Added a `.gitignore` for Python, local env files, and common editor artifacts.

## [0.2.0] - 2026-08-10

This release makes the project much easier to use in real environments.

- Split Bitbucket support into Cloud and Data Center connectors.
- Added project-based scan split (separate project keys for playbooks, roles, collections).
- Improved scan flow to support project filtering and cleaner repository selection.
- Added GraphQL-ready usage view for playbook -> role/collection mapping.
- Added a ready-to-use GraphQL example query file.
- Added community files: Code of Conduct and Security Policy.
- Simplified docs and naming across CLI/README.

## [0.1.0] - 2026-08-10

First usable version.

- Added Python CLI to run scans.
- Added Bitbucket scan and YAML extraction.
- Added Ansible parsing for playbooks, roles, collections, and dependencies.
- Added PostgreSQL storage with scan tracking.
- Added SQL views ready for GraphQL usage.
- Added setup docs and env template.
