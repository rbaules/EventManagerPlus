-- EventPlus: diagnostico de metadatos de solo lectura.
-- Ejecutar manualmente en Supabase SQL Editor y exportar cada resultado.
-- No habilita RLS, no crea politicas y no modifica el esquema.

select
  n.nspname as table_schema,
  c.relname as object_name,
  case c.relkind when 'r' then 'table' when 'v' then 'view'
       when 'm' then 'materialized_view' else c.relkind::text end as object_type,
  c.relrowsecurity as rls_enabled,
  c.relforcerowsecurity as rls_forced
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind in ('r', 'v', 'm')
order by c.relkind, c.relname;

select
  cols.table_schema, cols.table_name, cols.ordinal_position,
  cols.column_name, cols.data_type, cols.udt_name, cols.is_nullable,
  cols.column_default, cols.is_generated
from information_schema.columns cols
where cols.table_schema = 'public'
order by cols.table_name, cols.ordinal_position;

select
  tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type,
  kcu.column_name, kcu.ordinal_position,
  ccu.table_schema as foreign_table_schema,
  ccu.table_name as foreign_table_name,
  ccu.column_name as foreign_column_name
from information_schema.table_constraints tc
left join information_schema.key_column_usage kcu
  on kcu.constraint_schema = tc.constraint_schema
 and kcu.constraint_name = tc.constraint_name
left join information_schema.constraint_column_usage ccu
  on ccu.constraint_schema = tc.constraint_schema
 and ccu.constraint_name = tc.constraint_name
where tc.table_schema = 'public'
order by tc.table_name, tc.constraint_name, kcu.ordinal_position;

select schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_catalog.pg_policies
where schemaname = 'public'
order by tablename, policyname;

select grantor, grantee, table_schema, table_name, privilege_type, is_grantable
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated', 'PUBLIC')
order by table_name, grantee, privilege_type;

select grantor, grantee, table_schema, table_name, column_name, privilege_type
from information_schema.role_column_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated', 'PUBLIC')
order by table_name, column_name, grantee, privilege_type;

select
  n.nspname as function_schema, p.proname as function_name,
  pg_catalog.pg_get_function_identity_arguments(p.oid) as identity_arguments,
  p.prosecdef as security_definer,
  p.proconfig as function_settings,
  pg_catalog.pg_get_userbyid(p.proowner) as owner,
  pg_catalog.pg_get_functiondef(p.oid) as definition
from pg_catalog.pg_proc p
join pg_catalog.pg_namespace n on n.oid = p.pronamespace
where n.nspname in ('public', 'auth')
order by n.nspname, p.proname;

select
  event_object_schema, event_object_table, trigger_name,
  action_timing, event_manipulation, action_statement
from information_schema.triggers
where event_object_schema in ('public', 'auth')
order by event_object_schema, event_object_table, trigger_name;

select pub.pubname, n.nspname as table_schema, c.relname as table_name
from pg_catalog.pg_publication pub
join pg_catalog.pg_publication_rel pr on pr.prpubid = pub.oid
join pg_catalog.pg_class c on c.oid = pr.prrelid
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
order by pub.pubname, n.nspname, c.relname;

select
  n.nspname as view_schema, c.relname as view_name,
  coalesce(c.reloptions::text, '') as reloptions,
  pg_catalog.pg_get_viewdef(c.oid, true) as definition
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'v'
order by c.relname;
