-- Diagnostico de solo lectura. No aplica cambios ni habilita RLS.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'evp_eve_evento'
order by ordinal_position;

select tc.constraint_name, tc.constraint_type, kcu.column_name,
       ccu.table_name as foreign_table_name, ccu.column_name as foreign_column_name,
       cc.check_clause
from information_schema.table_constraints tc
left join information_schema.key_column_usage kcu
  on kcu.constraint_schema = tc.constraint_schema and kcu.constraint_name = tc.constraint_name
left join information_schema.constraint_column_usage ccu
  on ccu.constraint_schema = tc.constraint_schema and ccu.constraint_name = tc.constraint_name
left join information_schema.check_constraints cc
  on cc.constraint_schema = tc.constraint_schema and cc.constraint_name = tc.constraint_name
where tc.table_schema = 'public' and tc.table_name = 'evp_eve_evento'
order by tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

select trigger_name, action_timing, event_manipulation, action_statement
from information_schema.triggers
where event_object_schema = 'public' and event_object_table = 'evp_eve_evento'
order by trigger_name;

select schemaname, viewname, definition
from pg_catalog.pg_views
where schemaname = 'public' and definition ilike '%evp_eve_evento%'
order by viewname;

select n.nspname as function_schema, p.proname as function_name,
       pg_catalog.pg_get_function_identity_arguments(p.oid) as arguments,
       pg_catalog.pg_get_functiondef(p.oid) as definition
from pg_catalog.pg_proc p
join pg_catalog.pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and pg_catalog.pg_get_functiondef(p.oid) ilike '%evp_eve_evento%'
order by p.proname;

select indexname, indexdef
from pg_catalog.pg_indexes
where schemaname = 'public' and tablename = 'evp_eve_evento'
order by indexname;
