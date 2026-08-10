<p align="left">
  <img src="assets/ansiblemap-logo.svg" alt="AnsibleMap logo" width="500" />
</p>

[![GitHub release](https://img.shields.io/github/v/release/xbh03/AnsibleMap?label=release)](https://github.com/xbh03/AnsibleMap/releases)
[![License](https://img.shields.io/github/license/xbh03/AnsibleMap)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/xbh03/AnsibleMap?style=social)](https://github.com/xbh03/AnsibleMap/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/xbh03/AnsibleMap)](https://github.com/xbh03/AnsibleMap/issues)
[![Last commit](https://img.shields.io/github/last-commit/xbh03/AnsibleMap)](https://github.com/xbh03/AnsibleMap/commits)

AnsibleMap is a small pipeline that scans repositories, finds Ansible assets (playbooks, roles, collections), and saves their relationships in PostgreSQL.

The goal is simple: keep a clear map of "what uses what" and let the customer expose that data in their GraphQL layer.

Great for scheduled runs in Jenkins/cron or manual execution.

## Supported Python

- Python 3.11+

## What It Does

1. Connects to Bitbucket Cloud or Bitbucket Data Center repositories.
2. Reads YAML files and detects playbooks, roles, collections.
3. Extracts key dependencies (for example playbook -> role, role -> role, collection -> collection).
4. Stores everything in PostgreSQL.
5. Provides ready-to-use SQL views for GraphQL consumption.

## Quick Start

### 1) Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure env vars

Use `.env.example` as reference:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/ansiblemap'
export BITBUCKET_DEPLOYMENT='cloud'
export BITBUCKET_WORKSPACE='my-workspace'
export BITBUCKET_USERNAME='my-user'
export BITBUCKET_APP_PASSWORD='my-app-password'

# Optional cloud fallback auth
# export BITBUCKET_TOKEN='your-cloud-token'

# Optional split by project
export BITBUCKET_PROJECT_PLAYBOOKS='OPSPLAY'
export BITBUCKET_PROJECT_ROLES='OPSROLE'
export BITBUCKET_PROJECT_COLLECTIONS='OPSCOLL'

# Optional scan safety limits
export MAX_FILES_PER_REPO='2000'
export MAX_FILE_SIZE_BYTES='1048576'
```

### 3) Run a scan

Initialize DB schema once (recommended explicit step):

```bash
PYTHONPATH=src python -m ansiblemap.cli init-db
```

Notes:

- On PostgreSQL, `init-db` applies `sql/migrations/0001_init.sql`.
- On non-PostgreSQL engines (for local demos), `init-db` falls back to ORM schema creation.

Or apply SQL migration directly (Postgres):

```bash
psql "$DATABASE_URL" -f sql/migrations/0001_init.sql
```

Scan all repositories in the workspace:

```bash
PYTHONPATH=src python -m ansiblemap.cli scan-bitbucket
```

Scan specific repositories:

```bash
PYTHONPATH=src python -m ansiblemap.cli scan-bitbucket --repos repo-a,repo-b
```

Data Center example:

```bash
export BITBUCKET_DEPLOYMENT='datacenter'
export BITBUCKET_BASE_URL='https://bitbucket.company.tld'
export BITBUCKET_TOKEN='***'
PYTHONPATH=src python -m ansiblemap.cli scan-bitbucket
```

## GraphQL Data Views

Apply the provided views:

```bash
psql "$DATABASE_URL" -f sql/graphql_views.sql
```
Then expose tables and views in your GraphQL service (Hasura, PostGraphile, or custom API).

Ready-to-use GraphQL example:

- `graphql/example_queries.graphql`

## Authentication Notes

- Bitbucket Cloud primary mode: `BITBUCKET_USERNAME` + `BITBUCKET_APP_PASSWORD`.
- Bitbucket Cloud fallback mode: `BITBUCKET_TOKEN`.
- Bitbucket Data Center: token or username/password.

## Run Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

