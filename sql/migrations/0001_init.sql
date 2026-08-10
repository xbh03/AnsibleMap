-- Initial schema for AnsibleMap

create table if not exists scan_run (
  id integer generated always as identity primary key,
  provider varchar(50) not null,
  started_at timestamp not null,
  finished_at timestamp null,
  status varchar(20) not null,
  error_message text null
);

create table if not exists repository (
  id integer generated always as identity primary key,
  provider varchar(50) not null,
  external_id varchar(255) not null,
  slug varchar(255) not null,
  default_branch varchar(255) not null,
  constraint uq_repository_provider_external unique (provider, external_id)
);

create table if not exists artifact (
  id integer generated always as identity primary key,
  repo_id integer not null references repository(id),
  external_key varchar(600) not null,
  type varchar(50) not null,
  name varchar(255) not null,
  path varchar(1000) not null,
  fingerprint varchar(64) not null,
  metadata_json jsonb not null,
  constraint uq_artifact_repo_external_key unique (repo_id, external_key)
);

create table if not exists dependency (
  id integer generated always as identity primary key,
  from_artifact_id integer not null references artifact(id),
  to_artifact_id integer not null references artifact(id),
  dep_type varchar(50) not null,
  constraint uq_dependency_edge unique (from_artifact_id, to_artifact_id, dep_type)
);
