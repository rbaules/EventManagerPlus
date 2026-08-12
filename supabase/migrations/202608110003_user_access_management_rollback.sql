-- Rollback del incremento 8D. No revierte datos creados mientras estuvo aplicado.
drop function if exists public.evp_admin_buscar_usuario_para_cuenta(integer,text);
drop function if exists public.evp_admin_cambiar_estado_cuenta(uuid,integer,text);
drop function if exists public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer);
alter function public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text) rename to evp_admin_cambiar_estado_cuenta;
alter function public.evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer) rename to evp_admin_cambiar_rol_cuenta;
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
  if not a.usr_es_usuario_master and (r.ucu_rol not in ('Operador','Consulta') or p_nuevo_rol not in ('Operador','Consulta') or not exists(
    select 1 from public.evp_ucu_usuario_cuenta x where x.ucu_usuario_id=a.usr_usuario_id and x.ucu_cuenta_id=p_cuenta_id and x.ucu_rol='Administrador' and x.ucu_estado='Activo'
  )) then raise exception using errcode='P0001',message='ROLE_CHANGE_FORBIDDEN'; end if;
  if r.ucu_rol='Administrador' and p_nuevo_rol in ('Operador','Consulta') then
    if p_evento_id is null then raise exception using errcode='P0001',message='EVENT_REQUIRED'; end if;
    perform 1 from public.evp_eve_evento where eve_cuenta_id=p_cuenta_id and eve_evento_id=p_evento_id and eve_estado='Activo' for update;
    if not found then raise exception using errcode='P0001',message='INVALID_EVENT'; end if;
  end if;
  update public.evp_ucu_usuario_cuenta set ucu_rol=p_nuevo_rol where ucu_usuario_id=p_usuario_id and ucu_cuenta_id=p_cuenta_id;
  if r.ucu_rol='Administrador' and p_nuevo_rol in ('Operador','Consulta') then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo' where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
    insert into public.evp_uev_usuario_evento(uev_cuenta_id,uev_evento_id,uev_usuario_id,uev_estado)
    values(p_cuenta_id,p_evento_id,p_usuario_id,'Activo')
    on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
    update public.evp_usr_usuario set usr_cuenta_id_default=p_cuenta_id,usr_evento_id_default=p_evento_id where usr_usuario_id=p_usuario_id;
  elsif r.ucu_rol in ('Operador','Consulta') and p_nuevo_rol='Administrador' then
    update public.evp_uev_usuario_evento set uev_estado='Inactivo' where uev_usuario_id=p_usuario_id and uev_cuenta_id=p_cuenta_id;
    perform public.evp_priv_limpiar_defaults(p_usuario_id);
  else
    perform public.evp_priv_limpiar_defaults(p_usuario_id);
  end if;
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'cuenta_id',p_cuenta_id,'rol',p_nuevo_rol,'evento_id',p_evento_id);
end; $$;
grant execute on function public.evp_admin_cambiar_estado_cuenta(uuid,integer,text) to authenticated;
grant execute on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer) to authenticated;
drop function if exists public.evp_admin_cambiar_estado_evento_usuario(uuid,integer,integer,text);
drop function if exists public.evp_admin_agregar_evento_usuario(uuid,integer,integer);
drop function if exists public.evp_admin_agregar_cuenta_usuario(uuid,integer,text,integer);
drop function if exists public.evp_priv_8d_aplicar_transicion_rol(uuid,integer,text,text,integer,boolean);
