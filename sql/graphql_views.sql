-- Suggested DB contract for GraphQL layers like Hasura/PostGraphile

create or replace view v_artifact_usage as
select
  d.id as dependency_id,
  rf.slug as from_repository,
  af.type as from_type,
  af.name as from_name,
  af.path as from_path,
  d.dep_type,
  rt.slug as to_repository,
  at.type as to_type,
  at.name as to_name,
  at.path as to_path
from dependency d
join artifact af on af.id = d.from_artifact_id
join repository rf on rf.id = af.repo_id
join artifact at on at.id = d.to_artifact_id
join repository rt on rt.id = at.repo_id;

create or replace view v_playbook_role_map as
select
  rf.slug as repository,
  af.name as playbook,
  af.path as playbook_path,
  at.name as role,
  d.dep_type
from dependency d
join artifact af on af.id = d.from_artifact_id
join repository rf on rf.id = af.repo_id
join artifact at on at.id = d.to_artifact_id
where af.type = 'playbook' and at.type = 'role';

create or replace view v_playbook_usage as
select
  rf.slug as repository,
  af.name as playbook,
  af.path as playbook_path,
  at.type as used_type,
  at.name as used_name,
  rt.slug as used_repository,
  d.dep_type
from dependency d
join artifact af on af.id = d.from_artifact_id
join repository rf on rf.id = af.repo_id
join artifact at on at.id = d.to_artifact_id
join repository rt on rt.id = at.repo_id
where af.type = 'playbook' and at.type in ('role', 'collection');
