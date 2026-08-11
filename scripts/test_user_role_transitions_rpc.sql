-- Verificacion posterior a aplicar 202608100002 en un entorno controlado.
-- NO aplica la migracion. La seccion B escribe solamente dentro de BEGIN/ROLLBACK.

-- ============================================================================
-- A. VERIFICACION READ-ONLY
-- ============================================================================
do $$
declare
  n text; p record;
  trusted_owners constant text[] := array['postgres','supabase_admin'];
  current_functions constant text[] := array[
    'public.evp_admin_convertir_master(uuid)',
    'public.evp_admin_retirar_master(uuid,integer,text,integer)',
    'public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer)'
  ];
  obsolete_functions constant text[] := array[
    'public.evp_admin_cambiar_master(uuid,boolean)',
    'public.evp_admin_cambiar_rol_cuenta(uuid,integer,text)'
  ];
begin
  foreach n in array current_functions loop
    if to_regprocedure(n) is null then raise exception 'Falta RPC %',n; end if;
    select pr.prosecdef,pr.proconfig,pr.proacl,pg_get_userbyid(pr.proowner) owner_name
      into p from pg_proc pr where pr.oid=to_regprocedure(n);
    if not p.prosecdef then raise exception '% no es SECURITY DEFINER',n; end if;
    if not (p.proconfig @> array['search_path=""']::text[]) then raise exception '% no fija search_path vacio',n; end if;
    if not (p.owner_name=any(trusted_owners)) then raise exception '% tiene owner no confiable: %',n,p.owner_name; end if;
    if not has_function_privilege('authenticated',n,'execute') then raise exception 'authenticated sin EXECUTE en %',n; end if;
    if has_function_privilege('anon',n,'execute') then raise exception 'anon conserva EXECUTE en %',n; end if;
    if exists(select 1 from aclexplode(coalesce(p.proacl,acldefault('f',to_regrole(p.owner_name)))) a where a.grantee=0 and a.privilege_type='EXECUTE') then
      raise exception 'PUBLIC conserva EXECUTE en %',n;
    end if;
  end loop;
  foreach n in array obsolete_functions loop
    if to_regprocedure(n) is null then raise exception 'Falta firma historica esperada %',n; end if;
    if has_function_privilege('authenticated',n,'execute') or has_function_privilege('anon',n,'execute') then
      raise exception 'Firma obsoleta ejecutable por rol de aplicacion: %',n;
    end if;
    select pr.proacl,pr.proowner into p from pg_proc pr where pr.oid=to_regprocedure(n);
    if exists(select 1 from aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where a.grantee=0 and a.privilege_type='EXECUTE') then
      raise exception 'PUBLIC conserva EXECUTE en firma obsoleta %',n;
    end if;
  end loop;
end $$;

-- ============================================================================
-- B. PRUEBAS FUNCIONALES CON ESCRITURA
-- Requiere: un Master Activo con Auth, otro usuario Activo no Master, una cuenta
-- Activa y dos eventos Activos. Todo se descarta al final.
-- ============================================================================
begin;
do $$
declare
  actor public.evp_usr_usuario%rowtype; target public.evp_usr_usuario%rowtype;
  cid integer; e1 integer; e2 integer; other_cid integer; other_event integer;
  before_uev integer; active_uev integer;
begin
  select * into actor from public.evp_usr_usuario
  where usr_es_usuario_master and usr_estado='Activo' and usr_usuario_auth_uuid is not null
  order by usr_creado limit 1;
  if not found then raise exception 'FIXTURE_REQUIRED: Master Activo con Auth'; end if;
  select * into target from public.evp_usr_usuario
  where not usr_es_usuario_master and usr_estado='Activo' and usr_usuario_id<>actor.usr_usuario_id
  order by usr_creado limit 1;
  if not found then raise exception 'FIXTURE_REQUIRED: usuario Activo no Master'; end if;
  select e.eve_cuenta_id,min(e.eve_evento_id),max(e.eve_evento_id) into cid,e1,e2
  from public.evp_eve_evento e join public.evp_cta_cuenta c on c.cta_cuenta_id=e.eve_cuenta_id
  where c.cta_estado='Activo' and e.eve_estado='Activo'
  group by e.eve_cuenta_id having count(*)>=2 order by e.eve_cuenta_id limit 1;
  if cid is null then raise exception 'FIXTURE_REQUIRED: cuenta Activa con dos eventos Activos'; end if;
  perform set_config('request.jwt.claim.sub',actor.usr_usuario_auth_uuid::text,true);

  insert into public.evp_ucu_usuario_cuenta(ucu_cuenta_id,ucu_usuario_id,ucu_rol,ucu_estado)
  values(cid,target.usr_usuario_id,'Administrador','Activo')
  on conflict (ucu_cuenta_id,ucu_usuario_id) do update set ucu_rol='Administrador',ucu_estado='Activo';
  insert into public.evp_uev_usuario_evento values(cid,e1,target.usr_usuario_id,'Activo')
  on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  insert into public.evp_uev_usuario_evento values(cid,e2,target.usr_usuario_id,'Activo')
  on conflict (uev_cuenta_id,uev_evento_id,uev_usuario_id) do update set uev_estado='Activo';
  update public.evp_usr_usuario set usr_cuenta_id_default=cid,usr_evento_id_default=e1 where usr_usuario_id=target.usr_usuario_id;
  select count(*) into before_uev from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id;

  -- 1-5: Administrador -> Master.
  perform public.evp_admin_convertir_master(target.usr_usuario_id);
  if not (select usr_es_usuario_master from public.evp_usr_usuario where usr_usuario_id=target.usr_usuario_id) then raise exception 'Promocion no activo Master'; end if;
  if exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=target.usr_usuario_id and ucu_estado='Activo') then raise exception 'Promocion dejo UCU Activa'; end if;
  if (select count(*) from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id)<>before_uev then raise exception 'Promocion altero filas UEV'; end if;
  if not exists(select 1 from public.evp_usr_usuario where usr_usuario_id=target.usr_usuario_id and usr_cuenta_id_default=cid and usr_evento_id_default=e1) then raise exception 'Promocion perdio defaults activos'; end if;

  -- 6-9: Master -> Administrador.
  begin
    perform public.evp_admin_retirar_master(target.usr_usuario_id,cid,'Administrador',null);
    raise exception 'EXPECTED_EVENT_REQUIRED_NOT_RAISED';
  exception when others then
    if sqlerrm<>'EVENT_REQUIRED' then raise; end if;
  end;
  select e.eve_cuenta_id,e.eve_evento_id into other_cid,other_event
  from public.evp_eve_evento e join public.evp_cta_cuenta c on c.cta_cuenta_id=e.eve_cuenta_id
  where e.eve_cuenta_id<>cid and e.eve_estado='Activo' and c.cta_estado='Activo'
  order by e.eve_cuenta_id,e.eve_evento_id limit 1;
  if other_event is not null then
    begin
      perform public.evp_admin_retirar_master(target.usr_usuario_id,cid,'Administrador',other_event);
      raise exception 'EXPECTED_INVALID_EVENT_NOT_RAISED';
    exception when others then
      if sqlerrm<>'INVALID_EVENT' then raise; end if;
    end;
  else
    raise notice 'Caso evento de otra cuenta omitido: fixture sin segunda cuenta/evento Activos';
  end if;
  perform public.evp_admin_retirar_master(target.usr_usuario_id,cid,'Administrador',e1);
  if (select count(*) from public.evp_ucu_usuario_cuenta where ucu_usuario_id=target.usr_usuario_id and ucu_estado='Activo' and ucu_cuenta_id=cid and ucu_rol='Administrador')<>1 then raise exception 'Retiro Admin no dejo UCU Administrador Activa'; end if;
  if exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_estado='Activo') then raise exception 'Retiro Admin dejo UEV Activa'; end if;
  if not exists(select 1 from public.evp_usr_usuario where usr_usuario_id=target.usr_usuario_id and usr_cuenta_id_default=cid and usr_evento_id_default=e1) then raise exception 'Retiro Admin defaults incorrectos'; end if;

  -- 10-14: Master -> Operador y Master -> Consulta, una sola UEV Activa.
  perform public.evp_admin_convertir_master(target.usr_usuario_id);
  perform public.evp_admin_retirar_master(target.usr_usuario_id,cid,'Operador',e1);
  select count(*) into active_uev from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_estado='Activo';
  if active_uev<>1 or not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_evento_id=e1 and uev_estado='Activo') then raise exception 'Retiro Operador UEV incorrectas'; end if;
  perform public.evp_admin_convertir_master(target.usr_usuario_id);
  perform public.evp_admin_retirar_master(target.usr_usuario_id,cid,'Consulta',e2);
  select count(*) into active_uev from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_estado='Activo';
  if active_uev<>1 or not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_evento_id=e2 and uev_estado='Activo') then raise exception 'Retiro Consulta UEV incorrectas'; end if;

  -- 15-24: Administrador -> Operador/Consulta y retorno a Administrador.
  update public.evp_ucu_usuario_cuenta set ucu_rol='Administrador',ucu_estado='Activo' where ucu_usuario_id=target.usr_usuario_id and ucu_cuenta_id=cid;
  update public.evp_uev_usuario_evento set uev_estado='Activo' where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Operador',e1);
  if (select count(*) from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_estado='Activo')<>1 then raise exception 'Admin->Operador reactivo UEV historicas'; end if;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Administrador',null);
  if exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_estado='Activo') then raise exception 'Operador->Admin dejo UEV Activa'; end if;
  if not exists(select 1 from public.evp_usr_usuario where usr_usuario_id=target.usr_usuario_id and usr_evento_id_default=e1) then raise exception 'Operador->Admin perdio default heredado valido'; end if;
  update public.evp_uev_usuario_evento set uev_estado='Activo' where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Consulta',e2);
  if (select count(*) from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_estado='Activo')<>1 then raise exception 'Admin->Consulta reactivo UEV historicas'; end if;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Administrador',null);
  if exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_estado='Activo') then raise exception 'Consulta->Admin dejo UEV Activa'; end if;

  -- 25-26: Operador <-> Consulta conserva UEV.
  update public.evp_ucu_usuario_cuenta set ucu_rol='Operador' where ucu_usuario_id=target.usr_usuario_id and ucu_cuenta_id=cid;
  update public.evp_uev_usuario_evento set uev_estado=case when uev_evento_id=e1 then 'Activo' else 'Inactivo' end where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Consulta',null);
  if not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_evento_id=e1 and uev_estado='Activo') then raise exception 'Operador->Consulta altero UEV'; end if;
  perform public.evp_admin_cambiar_rol_cuenta(target.usr_usuario_id,cid,'Operador',null);
  if not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=target.usr_usuario_id and uev_cuenta_id=cid and uev_evento_id=e1 and uev_estado='Activo') then raise exception 'Consulta->Operador altero UEV'; end if;
end $$;
rollback;

-- ============================================================================
-- C. PRUEBAS CON JWT REALES
-- ============================================================================
-- Ejecutar en staging con tokens reales, nunca con service_role:
-- 27. JWT Administrador llama evp_admin_convertir_master: USER_ADMIN_FORBIDDEN.
-- 28. JWT Administrador llama evp_admin_retirar_master: USER_ADMIN_FORBIDDEN.
-- 29. JWT Administrador intenta p_nuevo_rol='Administrador': ROLE_CHANGE_FORBIDDEN.
-- 30. JWT Administrador cambia Operador <-> Consulta en su cuenta: OK.
-- 31. El mismo JWT usa cuenta ajena: ROLE_CHANGE_FORBIDDEN.
-- 32. JWT Master intenta retirar objetivo no Master: INVALID_MASTER_TRANSITION.
-- 33. JWT del unico Master Activo intenta retirarlo: LAST_MASTER.
-- 34. JWT Master intenta auto-retiro: SELF_MASTER_CHANGE_FORBIDDEN.
-- Confirmar despues de cada llamada que no hubo cambios parciales.

-- ============================================================================
-- D. PRUEBAS DE CONCURRENCIA
-- ============================================================================
-- Sesion 1: BEGIN; promover/retirar Master A; mantener transaccion abierta.
-- Sesion 2: BEGIN; promover/retirar Master B simultaneamente.
-- Esperado: sesion 2 espera advisory lock 817301; al continuar, reevalua actor,
-- objetivo y LAST_MASTER con datos confirmados, sin dejar cero Masters.
--
-- Misma UCU:
-- Sesion 1: BEGIN; cambiar Administrador -> Operador(evento 1), sin COMMIT.
-- Sesion 2: BEGIN; cambiar la misma UCU -> Consulta(evento 2).
-- Esperado: sesion 2 espera el FOR UPDATE de la UCU; despues aplica sobre el rol
-- confirmado. Nunca quedan dos ramas parcialmente aplicadas ni UEV reactivadas
-- fuera de la seleccion explicita. Finalizar ambas pruebas con ROLLBACK.
