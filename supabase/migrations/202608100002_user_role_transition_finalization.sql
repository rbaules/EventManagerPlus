-- Finalizacion incremental de transiciones de rol. No ejecutar desde la aplicacion.
-- Orden uniforme: advisory lock de Master -> actor -> objetivo -> cuenta -> UCU -> evento -> UEV.

revoke all on function public.evp_admin_cambiar_master(uuid,boolean) from public;
revoke all on function public.evp_admin_cambiar_master(uuid,boolean) from anon;
revoke all on function public.evp_admin_cambiar_master(uuid,boolean) from authenticated;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text) from public;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text) from anon;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text) from authenticated;

create or replace function public.evp_admin_convertir_master(p_usuario_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
begin
  perform pg_catalog.pg_advisory_xact_lock(817301);
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' or not a.usr_es_usuario_master then
    raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN';
  end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if t.usr_es_usuario_master then raise exception using errcode='P0001',message='INVALID_MASTER_TRANSITION'; end if;
  if t.usr_estado<>'Activo' then raise exception using errcode='P0001',message='INVALID_STATUS'; end if;

  update public.evp_usr_usuario set
    usr_es_usuario_master=true,
    usr_cuenta_id_default=case when exists(
      select 1 from public.evp_cta_cuenta c where c.cta_cuenta_id=t.usr_cuenta_id_default and c.cta_estado='Activo'
    ) then t.usr_cuenta_id_default else null end,
    usr_evento_id_default=case when exists(
      select 1 from public.evp_cta_cuenta c join public.evp_eve_evento e on e.eve_cuenta_id=c.cta_cuenta_id
      where c.cta_cuenta_id=t.usr_cuenta_id_default and c.cta_estado='Activo'
        and e.eve_evento_id=t.usr_evento_id_default and e.eve_estado='Activo'
    ) then t.usr_evento_id_default else null end
  where usr_usuario_id=p_usuario_id;
  update public.evp_ucu_usuario_cuenta set ucu_estado='Inactivo'
  where ucu_usuario_id=p_usuario_id and ucu_estado<>'Inactivo';
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'es_master',true);
end; $$;

create or replace function public.evp_admin_retirar_master(
  p_usuario_id uuid,p_cuenta_id integer,p_rol text,p_evento_id integer default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
begin
  if p_rol not in ('Administrador','Operador','Consulta') then
    raise exception using errcode='P0001',message='INVALID_ACCOUNT_ROLE';
  end if;
  if p_cuenta_id is null then raise exception using errcode='P0001',message='ACCOUNT_REQUIRED'; end if;
  if p_evento_id is null then
    raise exception using errcode='P0001',message='EVENT_REQUIRED';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(817301);
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' or not a.usr_es_usuario_master then
    raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN';
  end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if a.usr_usuario_id=t.usr_usuario_id then raise exception using errcode='P0001',message='SELF_MASTER_CHANGE_FORBIDDEN'; end if;
  if not t.usr_es_usuario_master then raise exception using errcode='P0001',message='INVALID_MASTER_TRANSITION'; end if;
  if t.usr_estado='Activo' and (select count(*) from public.evp_usr_usuario where usr_es_usuario_master and usr_estado='Activo')<=1 then
    raise exception using errcode='P0001',message='LAST_MASTER';
  end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and eve_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;

  update public.evp_ucu_usuario_cuenta set ucu_estado='Inactivo' where ucu_usuario_id=p_usuario_id;
  update public.evp_uev_usuario_evento set uev_estado='Inactivo' where uev_usuario_id=p_usuario_id;
  insert into public.evp_ucu_usuario_cuenta(ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado)
  values(p_cuenta_id,p_usuario_id,p_rol,'Activo')
  on conflict (ucu_cuenta_id,ucu_usuario_id) do update set ucu_rol=excluded.ucu_rol,ucu_estado='Activo';
  if p_rol in ('Operador','Consulta') then
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  end if;
  update public.evp_usr_usuario set usr_es_usuario_master=false,
    usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id
  where usr_usuario_id=p_usuario_id;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'es_master',false,
    'cuenta_id',p_cuenta_id,'rol',p_rol,'evento_id',p_evento_id);
end; $$;

create or replace function public.evp_admin_cambiar_rol_cuenta(
  p_usuario_id uuid,p_cuenta_id integer,p_nuevo_rol text,p_evento_id integer default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype; r public.evp_ucu_usuario_cuenta%rowtype;
begin
  if p_nuevo_rol not in ('Administrador','Operador','Consulta') then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found or t.usr_es_usuario_master then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  select * into r from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  if not found then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  if not a.usr_es_usuario_master and (
    r.ucu_rol not in ('Operador','Consulta') or p_nuevo_rol not in ('Operador','Consulta') or not exists(
      select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id
        and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo'
    )
  ) then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  if r.ucu_rol='Administrador' and p_nuevo_rol in ('Operador','Consulta') then
    if p_evento_id is null then raise exception using errcode='P0001',message='EVENT_REQUIRED'; end if;
    perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and eve_estado='Activo' for update;
    if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;
  end if;
  update public.evp_ucu_usuario_cuenta set ucu_rol=p_nuevo_rol where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id;
  if r.ucu_rol='Administrador' and p_nuevo_rol in ('Operador','Consulta') then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo'
    where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
    update public.evp_usr_usuario set usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id where usr_usuario_id=p_usuario_id;
  elsif r.ucu_rol in ('Operador','Consulta') and p_nuevo_rol='Administrador' then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo'
    where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
    perform public.evp_priv_limpiar_defaults(p_usuario_id);
  else
    perform public.evp_priv_limpiar_defaults(p_usuario_id);
  end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'rol',p_nuevo_rol,'evento_id',p_evento_id);
end; $$;

revoke all on function public.evp_admin_convertir_master(uuid) from public;
revoke all on function public.evp_admin_convertir_master(uuid) from anon;
revoke all on function public.evp_admin_convertir_master(uuid) from authenticated;
revoke all on function public.evp_admin_retirar_master(uuid,integer,text,integer) from public;
revoke all on function public.evp_admin_retirar_master(uuid,integer,text,integer) from anon;
revoke all on function public.evp_admin_retirar_master(uuid,integer,text,integer) from authenticated;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) from public;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) from anon;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) from authenticated;
grant execute on function public.evp_admin_convertir_master(uuid) to authenticated;
grant execute on function public.evp_admin_retirar_master(uuid,integer,text,integer) to authenticated;
grant execute on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) to authenticated;
