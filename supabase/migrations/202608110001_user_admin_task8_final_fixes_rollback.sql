-- Restaura las definiciones inmediatamente anteriores (202608100002 y 202608100001).

create or replace function public.evp_admin_convertir_master(p_usuario_id uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare a public.evp_usr_usuario%rowtype; t public.evp_usr_usuario%rowtype;
begin
  perform pg_catalog.pg_advisory_xact_lock(817301);
  select * into a from public.evp_usr_usuario where usr_usuario_auth_uuid=auth.uid() for update;
  if not found or a.usr_estado<>'Activo' or not a.usr_es_usuario_master then raise exception using errcode='P0001',message='USER_ADMIN_FORBIDDEN'; end if;
  select * into t from public.evp_usr_usuario where usr_usuario_id=p_usuario_id for update;
  if not found then raise exception using errcode='P0001',message='USER_NOT_FOUND'; end if;
  if t.usr_es_usuario_master then raise exception using errcode='P0001',message='INVALID_MASTER_TRANSITION'; end if;
  if t.usr_estado<>'Activo' then raise exception using errcode='P0001',message='INVALID_STATUS'; end if;
  update public.evp_usr_usuario set usr_es_usuario_master=true,
    usr_cuenta_id_default=case when exists(select 1 from public.evp_cta_cuenta c where c.cta_cuenta_id=t.usr_cuenta_id_default and c.cta_estado='Activo') then t.usr_cuenta_id_default else null end,
    usr_evento_id_default=case when exists(select 1 from public.evp_cta_cuenta c join public.evp_eve_evento e on e.eve_cuenta_id=c.cta_cuenta_id where c.cta_cuenta_id=t.usr_cuenta_id_default and c.cta_estado='Activo' and e.eve_evento_id=t.usr_evento_id_default and e.eve_estado='Activo') then t.usr_evento_id_default else null end
  where usr_usuario_id=p_usuario_id;
  update public.evp_ucu_usuario_cuenta set ucu_estado='Inactivo' where ucu_usuario_id=p_usuario_id and ucu_estado<>'Inactivo';
  return jsonb_build_object('ok',true,'codigo','OK','usuario_id',p_usuario_id,'es_master',true);
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

revoke all on function public.evp_admin_convertir_master(uuid) from public,anon,authenticated;
revoke all on function public.evp_admin_cambiar_estado_usuario(uuid,text) from public,anon,authenticated;
grant execute on function public.evp_admin_convertir_master(uuid) to authenticated;
grant execute on function public.evp_admin_cambiar_estado_usuario(uuid,text) to authenticated;
