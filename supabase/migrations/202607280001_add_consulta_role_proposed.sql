-- PROPUESTA NO EJECUTADA.
-- Requiere guardar primero el resultado de docs/RLS_METADATA_VALIDATION.md.
-- El contrato local documenta ucu_rol como varchar(20), no como enum.

begin;

do $$
declare
  v_data_type text;
  v_udt_name text;
  v_constraint record;
begin
  select c.data_type, c.udt_name
    into v_data_type, v_udt_name
  from information_schema.columns c
  where c.table_schema = 'public'
    and c.table_name = 'evp_ucu_usuario_cuenta'
    and c.column_name = 'ucu_rol';

  if v_data_type is null then
    raise exception 'No existe public.evp_ucu_usuario_cuenta.ucu_rol';
  end if;
  if v_data_type not in ('character varying', 'text', 'character') then
    raise exception 'Tipo de ucu_rol no validado: % (%)', v_data_type, v_udt_name;
  end if;

  for v_constraint in
    select con.conname, pg_get_constraintdef(con.oid) as definition
    from pg_constraint con
    join pg_class rel on rel.oid = con.conrelid
    join pg_namespace nsp on nsp.oid = rel.relnamespace
    where nsp.nspname = 'public'
      and rel.relname = 'evp_ucu_usuario_cuenta'
      and con.contype = 'c'
      and pg_get_constraintdef(con.oid) ilike '%ucu_rol%'
  loop
    if v_constraint.definition not ilike '%Administrador%'
       or v_constraint.definition not ilike '%Operador%'
       or (
         v_constraint.definition not ilike '%Consulta%'
         and v_constraint.definition !~* 'ARRAY.+Administrador.+Operador'
       ) then
      raise exception 'CHECK de ucu_rol inesperado: % = %',
        v_constraint.conname, v_constraint.definition;
    end if;
    execute format(
      'alter table public.evp_ucu_usuario_cuenta drop constraint %I',
      v_constraint.conname
    );
  end loop;
end
$$;

alter table public.evp_ucu_usuario_cuenta
  add constraint evp_ucu_usuario_cuenta_ucu_rol_check
  check (ucu_rol in ('Administrador', 'Operador', 'Consulta'))
  not valid;

alter table public.evp_ucu_usuario_cuenta
  validate constraint evp_ucu_usuario_cuenta_ucu_rol_check;

commit;
