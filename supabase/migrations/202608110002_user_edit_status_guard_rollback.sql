-- Restaura la definicion aplicada por 202608100001, sin guard de estado objetivo.

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

revoke all on function public.evp_admin_actualizar_usuario(uuid,text,text) from public,anon,authenticated;
grant execute on function public.evp_admin_actualizar_usuario(uuid,text,text) to authenticated;
