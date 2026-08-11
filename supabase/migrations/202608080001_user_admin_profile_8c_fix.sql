-- Correccion incremental 8C: trazabilidad, defaults atomicos y edicion del creador.
-- Requiere 202608060001_user_admin_profile_rpc.sql ya aplicada.

alter table public.evp_usr_usuario
  add column if not exists usr_creado_por uuid;

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname='fk_usr_creado_por' and conrelid='public.evp_usr_usuario'::regclass
  ) then
    alter table public.evp_usr_usuario
      add constraint fk_usr_creado_por foreign key (usr_creado_por)
      references public.evp_usr_usuario(usr_usuario_id) on delete set null;
  end if;
end $$;

drop function if exists public.evp_admin_crear_usuario(text,text,boolean,integer,text);

create or replace function public.evp_admin_crear_usuario(
  p_nombre text, p_email text, p_es_master boolean default false,
  p_cuenta_id integer default null, p_rol text default null,
  p_cuenta_default_id integer default null, p_evento_default_id integer default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_nombre text := regexp_replace(trim(coalesce(p_nombre,'')), '\s+', ' ', 'g');
  v_email text := lower(trim(coalesce(p_email,'')));
  v_id uuid;
  v_actor_id uuid;
  v_actor_master boolean;
  v_cuenta_default_id integer;
  v_evento_default_id integer;
  v_relacion_creada boolean := false;
  v_asignacion_evento_creada boolean := false;
begin
  if auth.uid() is null then raise exception using errcode='P0001', message='AUTH_REQUIRED'; end if;
  select u.usr_usuario_id,u.usr_es_usuario_master into v_actor_id,v_actor_master
    from public.evp_usr_usuario u
   where u.usr_usuario_auth_uuid=auth.uid() and u.usr_estado='Activo';
  if v_actor_id is null then raise exception using errcode='P0001', message='USER_ADMIN_FORBIDDEN'; end if;

  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001', message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
    raise exception using errcode='P0001', message='INVALID_EMAIL';
  end if;

  if not coalesce(v_actor_master,false) then
    if coalesce(p_es_master,false) then raise exception using errcode='P0001', message='USER_ADMIN_FORBIDDEN'; end if;
    if p_cuenta_id is null then raise exception using errcode='P0001', message='ACCOUNT_REQUIRED'; end if;
    if p_rol is null or trim(p_rol)='' then raise exception using errcode='P0001', message='ROLE_REQUIRED'; end if;
    if p_rol not in ('Operador','Consulta') then raise exception using errcode='P0001', message='INVALID_ACCOUNT_ROLE'; end if;
    if p_cuenta_default_id is not null or p_evento_default_id is not null then
      raise exception using errcode='P0001', message='DEFAULTS_FORBIDDEN';
    end if;
    if not exists (
      select 1 from public.evp_ucu_usuario_cuenta uc
      join public.evp_cta_cuenta c on c.cta_cuenta_id=uc.ucu_cuenta_id
      where uc.ucu_usuario_id=v_actor_id and uc.ucu_cuenta_id=p_cuenta_id
        and uc.ucu_rol='Administrador' and uc.ucu_estado='Activo' and c.cta_estado='Activo'
    ) then raise exception using errcode='P0001', message='ACCOUNT_FORBIDDEN'; end if;
  else
    if coalesce(p_es_master,false) then
      if p_rol is not null then raise exception using errcode='P0001', message='INVALID_ACCOUNT_ROLE'; end if;
      if p_cuenta_id is not null then raise exception using errcode='P0001', message='INVALID_ACCOUNT'; end if;
    elsif (p_cuenta_id is null) <> (p_rol is null) then
      raise exception using errcode='P0001', message=case when p_cuenta_id is null then 'ACCOUNT_REQUIRED' else 'ROLE_REQUIRED' end;
    elsif p_rol is not null and p_rol not in ('Administrador','Operador','Consulta') then
      raise exception using errcode='P0001', message='INVALID_ACCOUNT_ROLE';
    end if;
  end if;

  if p_cuenta_id is not null and not exists (
    select 1 from public.evp_cta_cuenta c where c.cta_cuenta_id=p_cuenta_id and c.cta_estado='Activo'
  ) then raise exception using errcode='P0001', message='INVALID_ACCOUNT'; end if;

  if p_cuenta_default_id is not null and not exists (
    select 1 from public.evp_cta_cuenta c where c.cta_cuenta_id=p_cuenta_default_id and c.cta_estado='Activo'
  ) then raise exception using errcode='P0001', message='INVALID_DEFAULT_ACCOUNT'; end if;
  if p_evento_default_id is not null and p_cuenta_default_id is null then
    raise exception using errcode='P0001', message='DEFAULT_ACCOUNT_REQUIRED';
  end if;
  if p_evento_default_id is not null and not exists (
    select 1 from public.evp_eve_evento e
    where e.eve_cuenta_id=p_cuenta_default_id and e.eve_evento_id=p_evento_default_id and e.eve_estado='Activo'
  ) then raise exception using errcode='P0001', message='INVALID_DEFAULT_EVENT'; end if;
  if not coalesce(p_es_master,false) and p_cuenta_default_id is not null
     and p_cuenta_default_id is distinct from p_cuenta_id then
    raise exception using errcode='P0001', message='DEFAULT_ACCOUNT_FORBIDDEN';
  end if;

  begin
    insert into public.evp_usr_usuario(
      usr_nombre_usuario,usr_nombre_usuario_abrev,usr_email,usr_es_usuario_master,
      usr_cuenta_id_default,usr_evento_id_default,usr_creado_por,usr_estado
    ) values (
      v_nombre,left(v_nombre,12),v_email,coalesce(p_es_master,false),
      null,null,v_actor_id,'Preregistrado'
    ) returning usr_usuario_id into v_id;
  exception when unique_violation then
    raise exception using errcode='P0001', message='USER_EMAIL_EXISTS';
  end;

  if p_cuenta_id is not null then
    insert into public.evp_ucu_usuario_cuenta(ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado)
    values(p_cuenta_id,v_id,p_rol,'Activo');
    v_relacion_creada := true;
  end if;
  if p_evento_default_id is not null and not coalesce(p_es_master,false)
     and p_rol in ('Operador','Consulta') then
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_default_id,p_evento_default_id,v_id,'Activo');
    v_asignacion_evento_creada := true;
  end if;

  -- Los triggers AFTER INSERT de las relaciones pueden proponer defaults. Esta
  -- escritura final conserva solamente las preferencias elegidas expresamente.
  -- Tambien fuerza que las FK de defaults se validen despues de crear relaciones.
  update public.evp_usr_usuario
     set usr_cuenta_id_default=p_cuenta_default_id,
         usr_evento_id_default=p_evento_default_id
   where usr_usuario_id=v_id
   returning usr_cuenta_id_default,usr_evento_id_default
        into v_cuenta_default_id,v_evento_default_id;

  return jsonb_build_object(
    'ok',true,'codigo','OK','usuario_id',v_id,'estado','Preregistrado',
    'es_master',coalesce(p_es_master,false),'cuenta_id',p_cuenta_id,'rol',p_rol,
    'cuenta_default_id',v_cuenta_default_id,'evento_default_id',v_evento_default_id,
    'relacion_cuenta_creada',v_relacion_creada,
    'asignacion_evento_creada',v_asignacion_evento_creada
  );
end;
$$;

create or replace function public.evp_admin_actualizar_usuario(
  p_usuario_id uuid,p_nombre text,p_email text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_nombre text := regexp_replace(trim(coalesce(p_nombre,'')), '\s+', ' ', 'g');
  v_email text := lower(trim(coalesce(p_email,'')));
  v_actor_id uuid;
  v_actor_master boolean;
  v_objetivo public.evp_usr_usuario%rowtype;
begin
  if auth.uid() is null then raise exception using errcode='P0001', message='AUTH_REQUIRED'; end if;
  select u.usr_usuario_id,u.usr_es_usuario_master into v_actor_id,v_actor_master
    from public.evp_usr_usuario u where u.usr_usuario_auth_uuid=auth.uid() and u.usr_estado='Activo';
  if v_actor_id is null then raise exception using errcode='P0001', message='USER_ADMIN_FORBIDDEN'; end if;
  select * into v_objetivo from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001', message='USER_NOT_FOUND'; end if;
  if not coalesce(v_actor_master,false) and (
    v_objetivo.usr_creado_por is distinct from v_actor_id or v_objetivo.usr_es_usuario_master
    or not exists (
      select 1
      from public.evp_ucu_usuario_cuenta actor_uc
      join public.evp_ucu_usuario_cuenta target_uc on target_uc.ucu_cuenta_id=actor_uc.ucu_cuenta_id
      join public.evp_cta_cuenta c on c.cta_cuenta_id=actor_uc.ucu_cuenta_id
      where actor_uc.ucu_usuario_id=v_actor_id and actor_uc.ucu_rol='Administrador'
        and actor_uc.ucu_estado='Activo' and target_uc.ucu_usuario_id=p_usuario_id
        and target_uc.ucu_estado='Activo' and c.cta_estado='Activo'
    )
  ) then
    raise exception using errcode='P0001', message='USER_EDIT_FORBIDDEN';
  end if;
  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001', message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then
    raise exception using errcode='P0001', message='INVALID_EMAIL';
  end if;
  begin
    update public.evp_usr_usuario set usr_nombre_usuario=v_nombre,
      usr_nombre_usuario_abrev=left(v_nombre,12),usr_email=v_email
    where usr_usuario_id=p_usuario_id;
  exception when unique_violation then raise exception using errcode='P0001', message='USER_EMAIL_EXISTS'; end;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id);
end;
$$;

revoke execute on function public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer) from public,anon;
revoke execute on function public.evp_admin_actualizar_usuario(uuid,text,text) from public,anon;
grant execute on function public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer) to authenticated;
grant execute on function public.evp_admin_actualizar_usuario(uuid,text,text) to authenticated;
