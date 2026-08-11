drop function if exists public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer);

create or replace function public.evp_admin_crear_usuario(
  p_nombre text,p_email text,p_es_master boolean default false,
  p_cuenta_id integer default null,p_rol text default null
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_nombre text:=regexp_replace(trim(coalesce(p_nombre,'')),'\s+',' ','g');
  v_email text:=lower(trim(coalesce(p_email,'')));
  v_id uuid; v_actor_id uuid; v_actor_master boolean; v_relacion_creada boolean:=false;
begin
  if auth.uid() is null then raise exception using errcode='P0001',message='AUTH_REQUIRED'; end if;
  select usr_usuario_id,usr_es_usuario_master into v_actor_id,v_actor_master
    from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() and usr_estado='Activo';
  if v_actor_id is null then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  if not coalesce(v_actor_master,false) then
    if coalesce(p_es_master,false) then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
    if p_cuenta_id is null then raise exception using errcode='P0001',message='ACCOUNT_REQUIRED'; end if;
    if p_rol is null or trim(p_rol)='' then raise exception using errcode='P0001',message='ROLE_REQUIRED'; end if;
    if p_rol not in ('Operador','Consulta') then raise exception using errcode='P0001',message='INVALID_ACCOUNT_ROLE'; end if;
    if not exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo') then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
    if not exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=v_actor_id and ucu_cuenta_id=p_cuenta_id and ucu_rol='Administrador' and ucu_estado='Activo') then raise exception using errcode='P0001',message='ACCOUNT_FORBIDDEN'; end if;
  elsif p_cuenta_id is null and p_rol is not null then raise exception using errcode='P0001',message='ACCOUNT_REQUIRED';
  elsif p_cuenta_id is not null then
    if p_rol is null or trim(p_rol)='' then raise exception using errcode='P0001',message='ROLE_REQUIRED'; end if;
    if p_rol not in ('Administrador','Operador','Consulta') then raise exception using errcode='P0001',message='INVALID_ACCOUNT_ROLE'; end if;
    if not exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=p_cuenta_id and cta_estado='Activo') then raise exception using errcode='P0001',message='INVALID_ACCOUNT'; end if;
  end if;
  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001',message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception using errcode='P0001',message='INVALID_EMAIL'; end if;
  begin
    insert into public.evp_usr_usuario(usr_nombre_usuario,usr_nombre_usuario_abrev,usr_email,usr_es_usuario_master,usr_estado)
    values(v_nombre,left(v_nombre,12),v_email,coalesce(p_es_master,false),'Preregistrado') returning usr_usuario_id into v_id;
  exception when unique_violation then raise exception using errcode='P0001',message='USER_EMAIL_EXISTS'; end;
  if p_cuenta_id is not null then
    insert into public.evp_ucu_usuario_cuenta(ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado) values(p_cuenta_id,v_id,p_rol,'Activo');
    v_relacion_creada:=true;
  end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',v_id,'estado','Preregistrado','es_master',coalesce(p_es_master,false),'cuenta_id',p_cuenta_id,'rol',p_rol,'relacion_cuenta_creada',v_relacion_creada);
end;
$$;

create or replace function public.evp_admin_actualizar_usuario(
  p_usuario_id uuid,p_nombre text,p_email text
) returns jsonb language plpgsql security definer set search_path='' as $$
declare
  v_nombre text:=regexp_replace(trim(coalesce(p_nombre,'')),'\s+',' ','g');
  v_email text:=lower(trim(coalesce(p_email,'')));
begin
  if auth.uid() is null then raise exception using errcode='P0001',message='AUTH_REQUIRED'; end if;
  if not public.evp_admin_actor_es_master() then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  if p_usuario_id is null then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if v_nombre='' or length(v_nombre)>50 then raise exception using errcode='P0001',message='INVALID_USER_NAME'; end if;
  if v_email='' or length(v_email)>254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception using errcode='P0001',message='INVALID_EMAIL'; end if;
  begin
    update public.evp_usr_usuario set usr_nombre_usuario=v_nombre,usr_nombre_usuario_abrev=left(v_nombre,12),usr_email=v_email where usr_usuario_id=p_usuario_id;
  exception when unique_violation then raise exception using errcode='P0001',message='USER_EMAIL_EXISTS'; end;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id);
end;
$$;

revoke execute on function public.evp_admin_crear_usuario(text,text,boolean,integer,text) from public,anon;
revoke execute on function public.evp_admin_actualizar_usuario(uuid,text,text) from public,anon;
grant execute on function public.evp_admin_crear_usuario(text,text,boolean,integer,text) to authenticated;
grant execute on function public.evp_admin_actualizar_usuario(uuid,text,text) to authenticated;

alter table public.evp_usr_usuario drop constraint if exists fk_usr_creado_por;
alter table public.evp_usr_usuario drop column if exists usr_creado_por;
