-- Administracion general UCU/UEV. Preparada localmente; no ejecutar desde la aplicacion.
-- Locks: actor -> objetivo -> cuenta -> UCU -> evento -> UEV.

alter function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer)
  rename to evp_priv_8d_cambiar_rol_cuenta;
alter function public.evp_admin_cambiar_estado_cuenta(uuid,integer,text)
  rename to evp_priv_8d_cambiar_estado_cuenta;
revoke all on function public.evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer) from public,anon,authenticated;
revoke all on function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) from public,anon,authenticated;
alter function public.evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer) security definer;
alter function public.evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer) set search_path='';
alter function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) security definer;
alter function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) set search_path='';

create function public.evp_priv_8d_aplicar_transicion_rol(
  p_usuario_id uuid,p_cuenta_id integer,p_rol_anterior text,p_rol_nuevo text,
  p_evento_id integer default null,p_es_reactivacion boolean default false
) returns void language plpgsql security definer set search_path='' as $$
begin
  if p_rol_anterior in ('Operador','Consulta') and p_rol_nuevo='Administrador' then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo'
    where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
  elsif p_rol_anterior='Administrador' and p_rol_nuevo in ('Operador','Consulta') then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo'
    where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  elsif p_es_reactivacion and p_rol_nuevo in ('Operador','Consulta') then
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  end if;
end; $$;
revoke all on function public.evp_priv_8d_aplicar_transicion_rol(uuid,integer,text,text,integer,boolean) from public,anon,authenticated;

create or replace function public.evp_priv_8d_cambiar_rol_cuenta(
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
  perform public.evp_priv_8d_aplicar_transicion_rol(p_usuario_id,p_cuenta_id,r.ucu_rol,p_nuevo_rol,p_evento_id,false);
  if r.ucu_rol='Administrador' and p_nuevo_rol in ('Operador','Consulta') then
    update public.evp_usr_usuario set usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id where usr_usuario_id=p_usuario_id;
  else
    perform public.evp_priv_limpiar_defaults(p_usuario_id);
  end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'rol',p_nuevo_rol,'evento_id',p_evento_id);
end; $$;

create function public.evp_admin_cambiar_rol_cuenta(p_usuario_id uuid,p_cuenta_id integer,p_nuevo_rol text,p_evento_id integer default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare s text;
begin
  select usr_estado into s from public.evp_usr_usuario where usr_usuario_id=p_usuario_id;
  if s not in ('Activo','Preregistrado') then raise exception using errcode='P0001',message='TARGET_STATUS_FORBIDDEN'; end if;
  return public.evp_priv_8d_cambiar_rol_cuenta(p_usuario_id,p_cuenta_id,p_nuevo_rol,p_evento_id);
end; $$;

create function public.evp_admin_cambiar_estado_cuenta(p_usuario_id uuid,p_cuenta_id integer,p_estado text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare s text;
begin
  select usr_estado into s from public.evp_usr_usuario where usr_usuario_id=p_usuario_id;
  if s not in ('Activo','Preregistrado') then raise exception using errcode='P0001',message='TARGET_STATUS_FORBIDDEN'; end if;
  return public.evp_priv_8d_cambiar_estado_cuenta(p_usuario_id,p_cuenta_id,p_estado);
end; $$;

create or replace function public.evp_admin_agregar_cuenta_usuario(
  p_usuario_id uuid, p_cuenta_id integer, p_rol text,
  p_evento_inicial_id integer default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
        r public.evp_ucu_usuario_cuenta%rowtype; existed boolean:=false;
        old_default_account integer; old_default_event integer;
begin
  if p_rol not in ('Administrador','Operador','Consulta') then raise exception using errcode='P0001',message='INVALID_ACCOUNT_ROLE'; end if;
  if p_rol in ('Operador','Consulta') and p_evento_inicial_id is null then raise exception using errcode='P0001',message='EVENT_REQUIRED'; end if;
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if t.usr_es_usuario_master then raise exception using errcode='P0001',message='ACCOUNT_RELATION_FORBIDDEN'; end if;
  old_default_account:=t.usr_cuenta_id_default; old_default_event:=t.usr_evento_id_default;
  if t.usr_estado not in ('Activo','Preregistrado') then raise exception using errcode='P0001',message='TARGET_STATUS_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  if not a.usr_es_usuario_master and (p_rol='Administrador' or not exists(
    select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id
      and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo'
  )) then raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN'; end if;
  select * into r from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  existed:=found;
  if existed and not a.usr_es_usuario_master and r.ucu_rol='Administrador' then raise exception using errcode='P0001',message='TARGET_ACCOUNT_ADMIN_FORBIDDEN'; end if;
  if existed and r.ucu_estado='Activo' then raise exception using errcode='P0001',message='ACCOUNT_RELATION_EXISTS'; end if;
  if p_rol in ('Operador','Consulta') then
    perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_inicial_id and eve_estado='Activo' for update;
    if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;
  end if;
  insert into public.evp_ucu_usuario_cuenta(ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado)
  values(p_cuenta_id,p_usuario_id,p_rol,'Activo')
  on conflict (ucu_cuenta_id,ucu_usuario_id) do update set ucu_rol=excluded.ucu_rol,ucu_estado='Activo';
  if existed then
    perform public.evp_priv_8d_aplicar_transicion_rol(p_usuario_id,p_cuenta_id,r.ucu_rol,p_rol,p_evento_inicial_id,true);
  elsif p_rol in ('Operador','Consulta') then
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_inicial_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  end if;
  update public.evp_usr_usuario set usr_cuenta_id_default=old_default_account,usr_evento_id_default=old_default_event
  where usr_usuario_id=p_usuario_id;
  perform public.evp_priv_limpiar_defaults(p_usuario_id);
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'rol',p_rol,'reactivada',existed);
end; $$;

create or replace function public.evp_admin_buscar_usuario_para_cuenta(
  p_cuenta_id integer,p_busqueda text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; q text; result jsonb;
begin
  q:=pg_catalog.lower(pg_catalog.btrim(coalesce(p_busqueda,'')));
  if pg_catalog.char_length(q)<3 then raise exception using errcode='P0001',message='SEARCH_TOO_SHORT'; end if;
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid();
  if not found or a.usr_estado<>'Activo' then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo';
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  if not a.usr_es_usuario_master and not exists(
    select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id
      and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo'
  ) then raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN'; end if;
  select coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
    'usuario_id',z.usr_usuario_id,'nombre',z.usr_nombre_usuario,'email',z.usr_email,
    'estado',z.usr_estado,'rol_cuenta',z.ucu_rol,'estado_relacion',z.ucu_estado
  ) order by z.usr_nombre_usuario,z.usr_email),'[]'::jsonb) into result
  from (
    select u.usr_usuario_id,u.usr_nombre_usuario,u.usr_email,u.usr_estado,r.ucu_rol,r.ucu_estado
    from public.evp_usr_usuario u
    left join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id and r.ucu_cuenta_id=p_cuenta_id
    where not u.usr_es_usuario_master and u.usr_estado in ('Activo','Preregistrado')
      and (pg_catalog.lower(u.usr_email)=q or pg_catalog.lower(u.usr_email) like '%'||q||'%'
        or pg_catalog.lower(u.usr_nombre_usuario) like '%'||q||'%')
    order by u.usr_nombre_usuario,u.usr_email limit 20
  ) z;
  return result;
end; $$;

create or replace function public.evp_admin_agregar_evento_usuario(
  p_usuario_id uuid,p_cuenta_id integer,p_evento_id integer
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
        r public.evp_ucu_usuario_cuenta%rowtype; oldstate text;
begin
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if t.usr_es_usuario_master or t.usr_estado not in ('Activo','Preregistrado') then raise exception using errcode='P0001',message='EVENT_RELATION_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  select * into r from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  if not found or r.ucu_estado<>'Activo' or r.ucu_rol not in ('Operador','Consulta') then raise exception using errcode='P0001',message='EVENT_RELATION_FORBIDDEN'; end if;
  if not a.usr_es_usuario_master and not exists(select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo') then raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN'; end if;
  perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and eve_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;
  select uev_estado into oldstate from public.evp_uev_usuario_evento where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id and uev_evento_id=p_evento_id for update;
  if found and oldstate='Activo' then raise exception using errcode='P0001',message='EVENT_RELATION_EXISTS'; end if;
  insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
  values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
  on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'evento_id',p_evento_id);
end; $$;

create or replace function public.evp_admin_cambiar_estado_evento_usuario(
  p_usuario_id uuid,p_cuenta_id integer,p_evento_id integer,p_estado text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
        r public.evp_ucu_usuario_cuenta%rowtype; oldstate text;
begin
  if p_estado not in ('Activo','Inactivo') then raise exception using errcode='P0001',message='INVALID_STATUS'; end if;
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if t.usr_es_usuario_master or t.usr_estado not in ('Activo','Preregistrado') then raise exception using errcode='P0001',message='EVENT_RELATION_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  select * into r from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  if not found or r.ucu_estado<>'Activo' or r.ucu_rol not in ('Operador','Consulta') then raise exception using errcode='P0001',message='EVENT_RELATION_FORBIDDEN'; end if;
  if not a.usr_es_usuario_master and not exists(select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo') then raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN'; end if;
  perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and (p_estado='Inactivo' or eve_estado='Activo') for update;
  if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;
  select uev_estado into oldstate from public.evp_uev_usuario_evento where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id and uev_evento_id=p_evento_id for update;
  if not found then raise exception using errcode='P0001',message='EVENT_RELATION_FORBIDDEN'; end if;
  update public.evp_uev_usuario_evento set uev_estado=p_estado where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id and uev_evento_id=p_evento_id;
  if p_estado='Inactivo' then perform public.evp_priv_limpiar_defaults(p_usuario_id); end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'evento_id',p_evento_id,'estado',p_estado);
end; $$;

revoke all on function public.evp_admin_agregar_cuenta_usuario(uuid,integer,text,integer) from public,anon,authenticated;
revoke all on function public.evp_admin_agregar_evento_usuario(uuid,integer,integer) from public,anon,authenticated;
revoke all on function public.evp_admin_cambiar_estado_evento_usuario(uuid,integer,integer,text) from public,anon,authenticated;
revoke all on function public.evp_admin_buscar_usuario_para_cuenta(integer,text) from public,anon,authenticated;
grant execute on function public.evp_admin_agregar_cuenta_usuario(uuid,integer,text,integer) to authenticated;
grant execute on function public.evp_admin_agregar_evento_usuario(uuid,integer,integer) to authenticated;
grant execute on function public.evp_admin_cambiar_estado_evento_usuario(uuid,integer,integer,text) to authenticated;
grant execute on function public.evp_admin_buscar_usuario_para_cuenta(integer,text) to authenticated;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) from public,anon,authenticated;
revoke all on function public.evp_admin_cambiar_estado_cuenta(uuid,integer,text) from public,anon,authenticated;
grant execute on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) to authenticated;
grant execute on function public.evp_admin_cambiar_estado_cuenta(uuid,integer,text) to authenticated;
