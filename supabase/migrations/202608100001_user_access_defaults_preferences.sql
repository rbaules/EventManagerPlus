-- Consolidacion incremental de acceso, defaults y preferencias.
-- Orden de bloqueo: actor -> objetivo -> cuenta -> relacion cuenta -> evento -> relacion evento.
-- No modifica migraciones 8C ya aplicadas.

create or replace function public.evp_priv_usuario_tiene_acceso(
  p_usuario_id uuid, p_cuenta_id integer, p_evento_id integer default null
) returns boolean language sql stable security definer set search_path='' as $$
  select exists (
    select 1 from public.evp_usr_usuario u
    join public.evp_cta_cuenta c on c.cta_cuenta_id=p_cuenta_id and c.cta_estado='Activo'
    where u.usr_usuario_id=p_usuario_id and u.usr_estado='Activo' and (
      u.usr_es_usuario_master or exists (
        select 1 from public.evp_ucu_usuario_cuenta uc
        where uc.ucu_usuario_id=u.usr_usuario_id and uc.ucu_cuenta_id=p_cuenta_id
          and uc.ucu_estado='Activo' and (
            (uc.ucu_rol='Administrador' and (p_evento_id is null or exists (
              select 1 from public.evp_eve_evento e where e.eve_cuenta_id=p_cuenta_id
                and e.eve_evento_id=p_evento_id and e.eve_estado='Activo'
            ))) or
            (uc.ucu_rol in ('Operador','Consulta') and (p_evento_id is null or exists (
              select 1 from public.evp_uev_usuario_evento ue
              join public.evp_eve_evento e on e.eve_cuenta_id=ue.uev_cuenta_id and e.eve_evento_id=ue.uev_evento_id
              where ue.uev_usuario_id=u.usr_usuario_id and ue.uev_cuenta_id=p_cuenta_id
                and ue.uev_evento_id=p_evento_id and ue.uev_estado='Activo' and e.eve_estado='Activo'
            )))
          )
      )
    )
  );
$$;

-- Elegibilidad de una preferencia persistida. A diferencia del acceso efectivo,
-- admite Preregistrado para conservar los defaults asignados durante su creación.
create or replace function public.evp_priv_usuario_puede_tener_default(
  p_usuario_id uuid, p_cuenta_id integer, p_evento_id integer default null
) returns boolean language sql stable security definer set search_path='' as $$
  select exists (
    select 1 from public.evp_usr_usuario u
    join public.evp_cta_cuenta c on c.cta_cuenta_id=p_cuenta_id and c.cta_estado='Activo'
    where u.usr_usuario_id=p_usuario_id and u.usr_estado in ('Activo','Preregistrado') and (
      u.usr_es_usuario_master or exists (
        select 1 from public.evp_ucu_usuario_cuenta uc
        where uc.ucu_usuario_id=u.usr_usuario_id and uc.ucu_cuenta_id=p_cuenta_id
          and uc.ucu_estado='Activo' and (
            (uc.ucu_rol='Administrador' and (p_evento_id is null or exists (
              select 1 from public.evp_eve_evento e where e.eve_cuenta_id=p_cuenta_id
                and e.eve_evento_id=p_evento_id and e.eve_estado='Activo'
            ))) or
            (uc.ucu_rol in ('Operador','Consulta') and (p_evento_id is null or exists (
              select 1 from public.evp_uev_usuario_evento ue
              join public.evp_eve_evento e on e.eve_cuenta_id=ue.uev_cuenta_id and e.eve_evento_id=ue.uev_evento_id
              where ue.uev_usuario_id=u.usr_usuario_id and ue.uev_cuenta_id=p_cuenta_id
                and ue.uev_evento_id=p_evento_id and ue.uev_estado='Activo' and e.eve_estado='Activo'
            )))
          )
      )
    )
  );
$$;

create or replace function public.evp_priv_limpiar_defaults(p_usuario_id uuid)
returns void language plpgsql security definer set search_path='' as $$
declare v public.evp_usr_usuario%rowtype;
begin
  select * into v from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then return; end if;
  if v.usr_cuenta_id_default is not null and not public.evp_priv_usuario_puede_tener_default(p_usuario_id,v.usr_cuenta_id_default,null) then
    update public.evp_usr_usuario set usr_cuenta_id_default=null,usr_evento_id_default=null where usr_usuario_id=p_usuario_id;
  elsif v.usr_evento_id_default is not null and not public.evp_priv_usuario_puede_tener_default(p_usuario_id,v.usr_cuenta_id_default,v.usr_evento_id_default) then
    update public.evp_usr_usuario set usr_evento_id_default=null where usr_usuario_id=p_usuario_id;
  end if;
end; $$;

-- Retirar todas las firmas históricas para que authenticated no pueda escoger
-- una ruta con reglas anteriores mediante sobrecarga.
drop function if exists public.evp_admin_crear_usuario(text,text,boolean);
drop function if exists public.evp_admin_crear_usuario(text,text,boolean,integer,text);
drop function if exists public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer);
create or replace function public.evp_admin_crear_usuario(
  p_nombre text,p_email text,p_rol text,p_cuenta_id integer,p_evento_id integer
) returns jsonb language plpgsql security definer set search_path='' as $$
declare v_actor public.evp_usr_usuario%rowtype; v_id uuid; v_nombre text; v_email text;
  v_ucu boolean:=false; v_uev boolean:=false; v_cd integer; v_ed integer;
begin
  if auth.uid() is null then raise exception using errcode='P0001',message='AUTH_REQUIRED'; end if;
  select * into v_actor from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  if p_rol not in ('Master','Administrador','Operador','Consulta') then raise exception using errcode='P0001',message='INVALID_ACCOUNT_ROLE'; end if;
  if not v_actor.usr_es_usuario_master and p_rol not in ('Operador','Consulta') then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta c where c.cta_cuenta_id=p_cuenta_id and c.cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='ACTIVE_CONTEXT_REQUIRED'; end if;
  perform 1 from public.evp_eve_evento e where e.eve_cuenta_id=p_cuenta_id and e.eve_evento_id=p_evento_id and e.eve_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='ACTIVE_CONTEXT_REQUIRED'; end if;
  if not v_actor.usr_es_usuario_master and not exists(select 1 from public.evp_ucu_usuario_cuenta uc where uc.ucu_usuario_id=v_actor.usr_usuario_id and uc.ucu_cuenta_id=p_cuenta_id and uc.ucu_rol='Administrador' and uc.ucu_estado='Activo') then
    raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN';
  end if;
  v_nombre:=regexp_replace(trim(coalesce(p_nombre,'')),'\s+',' ','g'); v_email:=lower(trim(coalesce(p_email,'')));
  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001',message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception using errcode='P0001',message='INVALID_EMAIL'; end if;
  begin
    insert into public.evp_usr_usuario(usr_nombre_usuario,usr_nombre_usuario_abrev,usr_email,usr_es_usuario_master,usr_cuenta_id_default,usr_evento_id_default,usr_creado_por,usr_estado)
    values(v_nombre,left(v_nombre,12),v_email,p_rol='Master',null,null,v_actor.usr_usuario_id,'Preregistrado') returning usr_usuario_id into v_id;
  exception when unique_violation then raise exception using errcode='P0001',message='USER_EMAIL_EXISTS'; end;
  if p_rol<>'Master' then
    insert into public.evp_ucu_usuario_cuenta values(p_cuenta_id,v_id,p_rol,'Activo'); v_ucu:=true;
  end if;
  if p_rol in ('Operador','Consulta') then
    insert into public.evp_uev_usuario_evento values(p_cuenta_id,p_evento_id,v_id,'Activo'); v_uev:=true;
  end if;
  update public.evp_usr_usuario set usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id
  where usr_usuario_id=v_id returning usr_cuenta_id_default,usr_evento_id_default into v_cd,v_ed;
  if v_cd is distinct from p_cuenta_id or v_ed is distinct from p_evento_id then raise exception using errcode='P0001',message='DEFAULT_PERSISTENCE_ERROR'; end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',v_id,'rol_inicial',p_rol,
    'cuenta_default_id',v_cd,'evento_default_id',v_ed,'relacion_cuenta_creada',v_ucu,'relacion_evento_creada',v_uev);
end; $$;

create or replace function public.evp_admin_actualizar_usuario(p_usuario_id uuid,p_nombre text,p_email text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare v_actor public.evp_usr_usuario%rowtype; v_target public.evp_usr_usuario%rowtype; v_nombre text; v_email text;
begin
  select * into v_actor from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into v_target from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if not v_actor.usr_es_usuario_master and (v_target.usr_es_usuario_master or not exists(
    select 1 from public.evp_ucu_usuario_cuenta a join public.evp_ucu_usuario_cuenta t on t.ucu_cuenta_id=a.ucu_cuenta_id
    join public.evp_cta_cuenta c on c.cta_cuenta_id=a.ucu_cuenta_id
    where a.ucu_usuario_id=v_actor.usr_usuario_id and a.ucu_rol='Administrador' and a.ucu_estado='Activo'
      and t.ucu_usuario_id=p_usuario_id and t.ucu_rol in ('Operador','Consulta') and t.ucu_estado='Activo' and c.cta_estado='Activo'
  )) then raise exception using errcode='P0001',message='USER_EDIT_FORBIDDEN'; end if;
  v_nombre:=regexp_replace(trim(coalesce(p_nombre,'')),'\s+',' ','g'); v_email:=lower(trim(coalesce(p_email,'')));
  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001',message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception using errcode='P0001',message='INVALID_EMAIL'; end if;
  begin update public.evp_usr_usuario set usr_nombre_usuario=v_nombre,usr_nombre_usuario_abrev=left(v_nombre,12),usr_email=v_email where usr_usuario_id=p_usuario_id;
  exception when unique_violation then raise exception using errcode='P0001',message='USER_EMAIL_EXISTS'; end;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id);
end; $$;

create or replace function public.evp_admin_cambiar_rol_cuenta(p_usuario_id uuid,p_cuenta_id integer,p_rol text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype; oldrol text;
begin
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found or t.usr_es_usuario_master then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  select ucu_rol into oldrol from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  if oldrol is null or p_rol not in ('Administrador','Operador','Consulta') then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  if not a.usr_es_usuario_master and (oldrol not in ('Operador','Consulta') or p_rol not in ('Operador','Consulta') or not exists(select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo')) then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  update public.evp_ucu_usuario_cuenta set ucu_rol=p_rol where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id;
  perform public.evp_priv_limpiar_defaults(p_usuario_id);
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'rol',p_rol);
end; $$;

create or replace function public.evp_admin_cambiar_estado_cuenta(p_usuario_id uuid,p_cuenta_id integer,p_estado text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype; r public.evp_ucu_usuario_cuenta%rowtype;
begin
  if p_estado not in ('Activo','Inactivo') then raise exception using errcode='P0001',message='INVALID_STATUS'; end if;
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='ACCOUNT_RELATION_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  select * into r from public.evp_ucu_usuario_cuenta where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id for update;
  if not found then raise exception using errcode='P0001',message='ACCOUNT_RELATION_FORBIDDEN'; end if;
  if t.usr_es_usuario_master or (not a.usr_es_usuario_master and (
    r.ucu_rol not in ('Operador','Consulta') or not exists(
      select 1 from public.evp_ucu_usuario_cuenta x
      where x.ucu_usuario_id=a.usr_usuario_id and x.ucu_cuenta_id=p_cuenta_id
        and x.ucu_rol='Administrador' and x.ucu_estado='Activo'
    )
  )) then raise exception using errcode='P0001',message='ACCOUNT_RELATION_FORBIDDEN'; end if;
  update public.evp_ucu_usuario_cuenta set ucu_estado=p_estado where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id;
  perform public.evp_priv_limpiar_defaults(p_usuario_id);
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'estado',p_estado);
end; $$;

create or replace function public.evp_usuario_actualizar_preferencias(p_cuenta_id integer,p_evento_id integer)
returns jsonb language plpgsql security definer set search_path='' as $$
declare u public.evp_usr_usuario%rowtype; cd integer; ed integer;
begin
  select * into u from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='AUTH_REQUIRED'; end if;
  perform 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo' for update;
  if not found then raise exception using errcode='P0001',message='INVALID_PREFERENCES'; end if;
  perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and eve_estado='Activo' for update;
  if not found or not public.evp_priv_usuario_tiene_acceso(u.usr_usuario_id,p_cuenta_id,p_evento_id) then raise exception using errcode='P0001',message='INVALID_PREFERENCES'; end if;
  update public.evp_usr_usuario set usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id where usr_usuario_id=u.usr_usuario_id returning usr_cuenta_id_default,usr_evento_id_default into cd,ed;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',u.usr_usuario_id,'cuenta_default_id',cd,'evento_default_id',ed);
end; $$;

create or replace function public.evp_admin_cambiar_estado_usuario(p_usuario_id uuid,p_estado text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
begin
  if p_estado not in ('Preregistrado','Activo','Inactivo') then raise exception using errcode='P0001',message='INVALID_STATUS'; end if;
  perform pg_catalog.pg_advisory_xact_lock(817301);
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo' for update;
  if not found or not a.usr_es_usuario_master then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if a.usr_usuario_id=p_usuario_id and p_estado='Inactivo' then raise exception using errcode='P0001',message='SELF_DEACTIVATION_FORBIDDEN'; end if;
  if p_estado='Activo' and t.usr_usuario_auth_uuid is null then raise exception using errcode='P0001',message='AUTH_REQUIRED'; end if;
  if t.usr_es_usuario_master and t.usr_estado='Activo' and p_estado='Inactivo' and (select count(*) from public.evp_usr_usuario where usr_es_usuario_master and usr_estado='Activo')<=1 then raise exception using errcode='P0001',message='LAST_MASTER'; end if;
  update public.evp_usr_usuario set usr_estado=p_estado,
    usr_cuenta_id_default=case when p_estado='Inactivo' then null else usr_cuenta_id_default end,
    usr_evento_id_default=case when p_estado='Inactivo' then null else usr_evento_id_default end
  where usr_usuario_id=p_usuario_id;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'estado',p_estado);
end; $$;

revoke all on function public.evp_priv_usuario_tiene_acceso(uuid,integer,integer) from public,anon,authenticated;
revoke all on function public.evp_priv_usuario_puede_tener_default(uuid,integer,integer) from public,anon,authenticated;
revoke all on function public.evp_priv_limpiar_defaults(uuid) from public,anon,authenticated;
revoke all on function public.evp_admin_crear_usuario(text,text,text,integer,integer) from public,anon;
revoke all on function public.evp_admin_actualizar_usuario(uuid,text,text) from public,anon;
revoke all on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text) from public,anon;
revoke all on function public.evp_admin_cambiar_estado_cuenta(uuid,integer,text) from public,anon;
revoke all on function public.evp_usuario_actualizar_preferencias(integer,integer) from public,anon;
revoke all on function public.evp_admin_cambiar_estado_usuario(uuid,text) from public,anon;
grant execute on function public.evp_admin_crear_usuario(text,text,text,integer,integer), public.evp_admin_actualizar_usuario(uuid,text,text), public.evp_admin_cambiar_rol_cuenta(uuid,integer,text), public.evp_admin_cambiar_estado_cuenta(uuid,integer,text), public.evp_usuario_actualizar_preferencias(integer,integer), public.evp_admin_cambiar_estado_usuario(uuid,text) to authenticated;
