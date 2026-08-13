-- Test manual de evp_admin_guardar_novedad_invitado.
-- A) metadatos; B) funcional BEGIN/ROLLBACK; C) concurrencia separada.
-- Por defecto no modifica tablas persistentes.
begin;

-- ACTIVACIÓN FUNCIONAL: descomentar SOLO la línea siguiente después de editar CONFIG.
-- do $$ begin perform set_config('eventplus.run_guest_incident_functional','on',true); end $$;

create temporary table guest_incident_test_results(
  orden integer primary key,
  prueba text not null,
  resultado text not null,
  detalle text not null
) on commit drop;

-- ================================================================
-- A. READ-ONLY: existencia, SECURITY DEFINER, search_path, owner y ACL.
-- ================================================================
do $$
declare
  signature constant text := 'public.evp_admin_guardar_novedad_invitado(uuid,text)';
  p oid; owner_name text; config text[];
begin
  p:=pg_catalog.to_regprocedure(signature);
  assert p is not null, signature||' no existe';
  select r.rolname,x.proconfig into owner_name,config
  from pg_catalog.pg_proc x join pg_catalog.pg_roles r on r.oid=x.proowner
  where x.oid=p;
  assert (select prosecdef from pg_catalog.pg_proc where oid=p), 'RPC no es SECURITY DEFINER';
  assert config @> array['search_path=""'], 'RPC no fija search_path vacío';
  assert owner_name=current_user or owner_name in ('postgres','supabase_admin'), 'Propietario no confiable';
  assert not exists(
    select 1 from pg_catalog.aclexplode(coalesce(
      (select proacl from pg_catalog.pg_proc where oid=p),
      pg_catalog.acldefault('f',(select proowner from pg_catalog.pg_proc where oid=p))
    )) a where a.grantee=0 and a.privilege_type='EXECUTE'
  ), 'PUBLIC conserva EXECUTE';
  assert not pg_catalog.has_function_privilege('anon',signature,'EXECUTE'), 'anon conserva EXECUTE';
  assert pg_catalog.has_function_privilege('authenticated',signature,'EXECUTE'), 'authenticated no tiene EXECUTE';
  raise notice 'PASS READ_ONLY: firma, SECURITY DEFINER, search_path, owner y ACL';
end $$;

-- ================================================================
-- B. FUNCIONAL AUTOCONTENIDA. Todo queda dentro de BEGIN/ROLLBACK.
-- ================================================================
do $$
declare
  -- CONFIG cerrada con fixtures reales auditadas el 12-08-2026.
  master_auth constant uuid := '397bc597-6e61-4447-a222-dcdb55051f7b';
  operator_auth constant uuid := 'a3b47ae0-2824-4763-941c-4b38d9785994';
  consulta_auth constant uuid := 'f85e972f-8c72-4556-a302-10b419ee5a7e';
  expected_master_id constant uuid := 'c14208de-e66d-4f0b-864c-15d6720734d9';
  expected_operator_id constant uuid := 'a73f0cf1-e655-4126-bd4e-1020278af9c9';
  expected_consulta_id constant uuid := '2ff1d503-9a55-4e3c-848b-573ee138c378';
  writable_account constant integer := 2;
  writable_event constant integer := 1;
  operator_denied_event constant integer := 2;
  admin_other_account constant integer := 3;
  readonly_account constant integer := 2;
  readonly_event constant integer := 4;

  synthetic_guest constant uuid := '8f120001-0000-4000-8000-000000000001';
  operator_denied_guest constant uuid := '8f120003-0000-4000-8000-000000000003';
  readonly_guest constant uuid := '8f120002-0000-4000-8000-000000000002';
  master_id uuid; operator_id uuid; consulta_id uuid;
  invitation_id integer; denied_invitation_id integer; readonly_invitation_id integer;
  response jsonb; created_at timestamptz; modified_at timestamptz; created_by uuid;
  master_modificado timestamptz; operator_modificado timestamptz; consulta_modificado timestamptz;
begin
  if coalesce(current_setting('eventplus.run_guest_incident_functional',true),'off')<>'on' then
    raise notice 'Funcional omitida: eventplus.run_guest_incident_functional no está en on';
    return;
  end if;

  -- Precondiciones de identidades y alcance; auth.users nunca se modifica.
  select usr_usuario_id into master_id from public.evp_usr_usuario
   where usr_usuario_auth_uuid=master_auth and usr_estado='Activo' and usr_es_usuario_master;
  assert found and master_id=expected_master_id, 'CONFIG MASTER inválida';
  select u.usr_usuario_id into operator_id from public.evp_usr_usuario u
    join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id
    join public.evp_uev_usuario_evento a on a.uev_usuario_id=u.usr_usuario_id and a.uev_cuenta_id=r.ucu_cuenta_id
   where u.usr_usuario_auth_uuid=operator_auth and u.usr_estado='Activo' and not u.usr_es_usuario_master
     and r.ucu_cuenta_id=writable_account and r.ucu_rol='Operador' and r.ucu_estado='Activo'
     and a.uev_evento_id=writable_event and a.uev_estado='Activo';
  assert found and operator_id=expected_operator_id, 'CONFIG OPERATOR sin UCU+UEV';
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=operator_id
    and ucu_cuenta_id=3 and ucu_rol='Operador' and ucu_estado='Activo'), 'Operador cambió UCU Cuenta 3';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=2 and uev_evento_id=1 and uev_estado='Activo'), 'Operador cambió UEV Cuenta 2/Evento 1';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=2 and uev_evento_id=2 and uev_estado='Inactivo'), 'Operador cambió UEV Cuenta 2/Evento 2';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=3 and uev_evento_id=1 and uev_estado='Activo'), 'Operador cambió UEV Cuenta 3/Evento 1';
  assert not exists(select 1 from public.evp_uev_usuario_evento a
    where a.uev_usuario_id=operator_id and a.uev_cuenta_id=writable_account
      and a.uev_evento_id=operator_denied_event and a.uev_estado='Activo'), 'Operador obtuvo UEV Activa inesperada en Evento 2';
  select u.usr_usuario_id into consulta_id from public.evp_usr_usuario u
    join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id
    join public.evp_uev_usuario_evento a on a.uev_usuario_id=u.usr_usuario_id and a.uev_cuenta_id=r.ucu_cuenta_id
   where u.usr_usuario_auth_uuid=consulta_auth and u.usr_estado='Activo' and not u.usr_es_usuario_master
     and r.ucu_cuenta_id=writable_account and r.ucu_rol='Consulta' and r.ucu_estado='Activo'
     and a.uev_evento_id=writable_event and a.uev_estado='Activo';
  assert found and consulta_id=expected_consulta_id, 'CONFIG CONSULTA sin UCU+UEV';
  select usr_modificado into master_modificado from public.evp_usr_usuario where usr_usuario_id=master_id;
  select usr_modificado into operator_modificado from public.evp_usr_usuario where usr_usuario_id=operator_id;
  select usr_modificado into consulta_modificado from public.evp_usr_usuario where usr_usuario_id=consulta_id;
  assert exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=writable_account and cta_estado='Activo');
  assert exists(select 1 from public.evp_eve_evento where eve_cuenta_id=writable_account and eve_evento_id=writable_event
    and eve_estado='Activo' and eve_fase_evento='En_proceso');
  assert exists(select 1 from public.evp_eve_evento where eve_cuenta_id=writable_account and eve_evento_id=operator_denied_event
    and eve_estado='Activo' and eve_fase_evento='Pre_evento');
  assert exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=readonly_account and cta_estado='Activo');
  assert exists(select 1 from public.evp_eve_evento where eve_cuenta_id=readonly_account and eve_evento_id=readonly_event
    and eve_estado='Activo' and eve_fase_evento='Pre_evento');
  assert not exists(select 1 from public.evp_ivt_invitado where ivt_invitado_uuid in (synthetic_guest,operator_denied_guest,readonly_guest));
  assert not exists(select 1 from public.evp_ivt_invitado where ivt_cuenta_id=writable_account
    and ivt_evento_id=writable_event and ivt_nombre_invitado_normalizado=public.evp_normalizar_texto('RPC Novedad Test')),
    'Nombre sintético ya existe en evento escribible';
  assert not exists(select 1 from public.evp_ivt_invitado where ivt_cuenta_id=writable_account
    and ivt_evento_id=operator_denied_event and ivt_nombre_invitado_normalizado=public.evp_normalizar_texto('RPC Novedad Denied')),
    'Nombre sintético ya existe en evento sin UEV';
  assert not exists(select 1 from public.evp_ivt_invitado where ivt_cuenta_id=readonly_account
    and ivt_evento_id=readonly_event and ivt_nombre_invitado_normalizado=public.evp_normalizar_texto('RPC Novedad Readonly')),
    'Nombre sintético ya existe en evento read-only';

  -- Targets sintéticos mínimos: invitación + invitado, sin mesa. Los triggers asignan IDs.
  insert into public.evp_inv_invitacion(inv_cuenta_id,inv_evento_id,inv_destinatario_invitacion,inv_cant_puestos_reservados,inv_estado)
  values(writable_account,writable_event,'RPC Novedad Test',1,'Activo') returning inv_invitacion_id into invitation_id;
  insert into public.evp_ivt_invitado(ivt_cuenta_id,ivt_evento_id,ivt_invitacion_id,ivt_invitado_uuid,
    ivt_nombre_invitado,ivt_es_invitado_principal,ivt_es_invitado_imprevisto,ivt_llegada_confirmada,ivt_tiene_novedad,ivt_estado)
  values(writable_account,writable_event,invitation_id,synthetic_guest,'RPC Novedad Test',true,false,false,false,'Activo');
  insert into public.evp_inv_invitacion(inv_cuenta_id,inv_evento_id,inv_destinatario_invitacion,inv_cant_puestos_reservados,inv_estado)
  values(writable_account,operator_denied_event,'RPC Novedad Denied',1,'Activo') returning inv_invitacion_id into denied_invitation_id;
  insert into public.evp_ivt_invitado(ivt_cuenta_id,ivt_evento_id,ivt_invitacion_id,ivt_invitado_uuid,
    ivt_nombre_invitado,ivt_es_invitado_principal,ivt_es_invitado_imprevisto,ivt_llegada_confirmada,ivt_tiene_novedad,ivt_estado)
  values(writable_account,operator_denied_event,denied_invitation_id,operator_denied_guest,'RPC Novedad Denied',true,false,false,false,'Activo');
  update public.evp_eve_evento set eve_fase_evento='Post_evento'
  where eve_cuenta_id=readonly_account and eve_evento_id=readonly_event and eve_fase_evento='Pre_evento';
  assert found, 'No se pudo preparar fase temporal Post_evento';
  insert into public.evp_inv_invitacion(inv_cuenta_id,inv_evento_id,inv_destinatario_invitacion,inv_cant_puestos_reservados,inv_estado)
  values(readonly_account,readonly_event,'RPC Novedad Readonly',1,'Activo') returning inv_invitacion_id into readonly_invitation_id;
  insert into public.evp_ivt_invitado(ivt_cuenta_id,ivt_evento_id,ivt_invitacion_id,ivt_invitado_uuid,
    ivt_nombre_invitado,ivt_es_invitado_principal,ivt_es_invitado_imprevisto,ivt_llegada_confirmada,ivt_tiene_novedad,ivt_estado)
  values(readonly_account,readonly_event,readonly_invitation_id,readonly_guest,'RPC Novedad Readonly',true,false,false,false,'Activo');

  perform set_config('request.jwt.claim.sub',master_auth::text,true); assert auth.uid()=master_auth,'AUTH MASTER_CREATE';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Master crea');
  assert response->>'codigo'='OK' and (response->>'tiene_novedad')::boolean;
  insert into guest_incident_test_results values(10,'MASTER_CREATE','PASS','Master creó la novedad');
  select ivt_novedad_creada,ivt_novedad_creada_por into created_at,created_by from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest;

  perform set_config('request.jwt.claim.sub',master_auth::text,true); assert auth.uid()=master_auth,'AUTH MASTER_EDIT';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Master edita'); assert response->>'codigo'='OK';
  assert (select ivt_descripcion_novedad='Master edita' from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(20,'MASTER_EDIT','PASS','Master editó la novedad');

  perform set_config('request.jwt.claim.sub',master_auth::text,true); assert auth.uid()=master_auth,'AUTH MASTER_CLEAR';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,null); assert response->>'codigo'='OK';
  assert (select not ivt_tiene_novedad and ivt_descripcion_novedad is null from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(30,'MASTER_CLEAR','PASS','Master limpió lógicamente la novedad');

  -- Admin temporal: reutiliza las dos UCU físicas del Operador sin cambiar sus PK.
  -- Cuenta 3 queda Administrador/Activo y Cuenta 2 Operador/Inactivo.
  update public.evp_ucu_usuario_cuenta set ucu_rol='Administrador'
    where ucu_usuario_id=operator_id and ucu_cuenta_id=admin_other_account
      and ucu_rol='Operador' and ucu_estado='Activo';
  assert found, 'No se pudo preparar Admin temporal en Cuenta 3';
  update public.evp_ucu_usuario_cuenta set ucu_estado='Inactivo'
    where ucu_usuario_id=operator_id and ucu_cuenta_id=writable_account
      and ucu_rol='Operador' and ucu_estado='Activo';
  assert found, 'No se pudo inactivar temporalmente Operador en Cuenta 2';
  perform set_config('request.jwt.claim.sub',operator_auth::text,true); assert auth.uid()=operator_auth,'AUTH ADMIN_OTHER';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'No guardar'); assert response->>'codigo'='FORBIDDEN';
  insert into guest_incident_test_results values(50,'ADMIN_FORBIDDEN_OTHER_ACCOUNT','PASS','Administrador ajeno rechazado');

  update public.evp_ucu_usuario_cuenta set ucu_rol='Administrador',ucu_estado='Activo'
    where ucu_usuario_id=operator_id and ucu_cuenta_id=writable_account
      and ucu_rol='Operador' and ucu_estado='Inactivo';
  assert found, 'No se pudo preparar Admin autorizado en Cuenta 2';
  perform set_config('request.jwt.claim.sub',operator_auth::text,true); assert auth.uid()=operator_auth,'AUTH ADMIN_CREATE';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Admin crea'); assert response->>'codigo'='OK';
  insert into guest_incident_test_results values(40,'ADMIN_CREATE','PASS','Administrador autorizado guardó');

  -- Restauración explícita antes de cualquier caso Operador.
  update public.evp_ucu_usuario_cuenta set ucu_rol='Operador',ucu_estado='Activo'
    where ucu_usuario_id=operator_id and ucu_cuenta_id in (writable_account,admin_other_account)
      and ucu_rol='Administrador' and ucu_estado='Activo';
  assert (select count(*) from public.evp_ucu_usuario_cuenta where ucu_usuario_id=operator_id
    and ucu_cuenta_id in (writable_account,admin_other_account)
    and ucu_rol='Operador' and ucu_estado='Activo')=2, 'No se restauraron ambas UCU Operador';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=2 and uev_evento_id=1 and uev_estado='Activo');
  assert not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=2 and uev_evento_id=2 and uev_estado='Activo');
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=3 and uev_evento_id=1 and uev_estado='Activo');

  perform set_config('request.jwt.claim.sub',operator_auth::text,true); assert auth.uid()=operator_auth,'AUTH OPERATOR_CREATE';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Operador crea'); assert response->>'codigo'='OK';
  insert into guest_incident_test_results values(60,'OPERATOR_CREATE','PASS','Operador con UCU+UEV guardó');

  perform set_config('request.jwt.claim.sub',operator_auth::text,true); assert auth.uid()=operator_auth,'AUTH OPERATOR_WITHOUT_UEV';
  assert not exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=operator_id
    and uev_cuenta_id=writable_account and uev_evento_id=operator_denied_event and uev_estado='Activo');
  response:=public.evp_admin_guardar_novedad_invitado(operator_denied_guest,'No guardar'); assert response->>'codigo'='FORBIDDEN';
  insert into guest_incident_test_results values(70,'OPERATOR_WITHOUT_UEV','PASS','Operador sin UEV rechazado');

  -- Consulta nunca se utilizó ni modificó como Admin temporal.
  perform set_config('request.jwt.claim.sub',consulta_auth::text,true); assert auth.uid()=consulta_auth,'AUTH CONSULTA';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'No guardar'); assert response->>'codigo'='CONSULTA_READ_ONLY';
  insert into guest_incident_test_results values(80,'CONSULTA_READ_ONLY','PASS','Consulta rechazado explícitamente');

  perform set_config('request.jwt.claim.sub',master_auth::text,true); assert auth.uid()=master_auth,'AUTH DESCRIPTION';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,repeat('x',200)); assert response->>'codigo'='OK';
  insert into guest_incident_test_results values(90,'DESCRIPTION_200_OK','PASS','200 caracteres aceptados');
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,repeat('x',201)); assert response->>'codigo'='DESCRIPTION_TOO_LONG';
  assert (select char_length(ivt_descripcion_novedad)=200 from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(100,'DESCRIPTION_201_REJECTED','PASS','201 caracteres rechazados sin alterar contenido');
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'   '); assert response->>'codigo'='OK';
  assert (select not ivt_tiene_novedad and ivt_descripcion_novedad is null from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(110,'BLANK_CLEARS','PASS','Espacios producen limpieza lógica');

  -- Reinicio controlado del target sintético para probar una primera creación limpia.
  update public.evp_ivt_invitado set ivt_tiene_novedad=false,ivt_descripcion_novedad=null,
    ivt_novedad_creada=null,ivt_novedad_creada_por=null,ivt_novedad_mod=null,ivt_novedad_mod_por=null
  where ivt_invitado_uuid=synthetic_guest;
  perform set_config('request.jwt.claim.sub',operator_auth::text,true); assert auth.uid()=operator_auth,'AUTH TRACE_CREATE';
  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Trace create'); assert response->>'codigo'='OK';
  select ivt_novedad_creada,ivt_novedad_creada_por into created_at,created_by from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest;
  assert created_at is not null and created_by=operator_id;
  assert (select ivt_novedad_mod is null and ivt_novedad_mod_por is null from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(120,'TRACE_CREATE','PASS','Creación y actor establecidos; modificación nula');

  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,'Trace edit'); assert response->>'codigo'='OK';
  select ivt_novedad_mod into modified_at from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest;
  assert modified_at is not null;
  assert (select ivt_novedad_creada=created_at and ivt_novedad_creada_por=created_by and ivt_novedad_mod_por=operator_id
    from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(130,'TRACE_EDIT','PASS','Creación preservada; modificación y actor actualizados');

  response:=public.evp_admin_guardar_novedad_invitado(synthetic_guest,null); assert response->>'codigo'='OK';
  assert (select not ivt_tiene_novedad and ivt_descripcion_novedad is null and ivt_novedad_creada=created_at
    and ivt_novedad_creada_por=created_by and ivt_novedad_mod>=modified_at and ivt_novedad_mod_por=operator_id
    from public.evp_ivt_invitado where ivt_invitado_uuid=synthetic_guest);
  insert into guest_incident_test_results values(140,'TRACE_CLEAR','PASS','Limpieza preservó creación y actualizó modificación');

  perform set_config('request.jwt.claim.sub',master_auth::text,true); assert auth.uid()=master_auth,'AUTH EVENT_PHASE';
  response:=public.evp_admin_guardar_novedad_invitado(readonly_guest,'No guardar'); assert response->>'codigo'='EVENT_PHASE_READ_ONLY';
  insert into guest_incident_test_results values(150,'EVENT_PHASE_READ_ONLY','PASS','Post_evento/Cerrado rechazado');

  assert (select usr_modificado is not distinct from master_modificado from public.evp_usr_usuario where usr_usuario_id=master_id),
    'Perfil global Master fue modificado';
  assert (select usr_modificado is not distinct from operator_modificado from public.evp_usr_usuario where usr_usuario_id=operator_id),
    'Perfil global Operador fue modificado';
  assert (select usr_modificado is not distinct from consulta_modificado from public.evp_usr_usuario where usr_usuario_id=consulta_id),
    'Perfil global Consulta fue modificado';
  assert (select count(*) from guest_incident_test_results where resultado='PASS')=15,'SUMMARY distinto de 15 PASS';
  insert into guest_incident_test_results values(160,'SUMMARY','PASS','15/15 pruebas funcionales superadas');
  raise notice 'PASS FUNCTIONAL: 15/15; ROLLBACK elimina invitaciones e invitados sintéticos';
end $$;

-- Resultado tabular. Queda vacío si no se activó el bloque funcional.
select orden,prueba,resultado,detalle from guest_incident_test_results order by orden;
rollback;

-- ================================================================
-- C. CONCURRENCIA EN DOS SESIONES (NO EJECUTAR TODAVÍA)
-- ================================================================
-- Usar un invitado de prueba y un actor autorizado. Sustituir UUID_AUTH/UUID_INVITADO.
-- SESSION A:
--   begin;
--   select set_config('request.jwt.claim.sub','UUID_AUTH',true);
--   select auth.uid();
--   select public.evp_admin_guardar_novedad_invitado('UUID_INVITADO','Sesión A');
--   -- mantener abierta sin COMMIT.
-- SESSION B, mientras A sigue abierta:
--   begin;
--   select set_config('request.jwt.claim.sub','UUID_AUTH',true);
--   select auth.uid();
--   select public.evp_admin_guardar_novedad_invitado('UUID_INVITADO','Sesión B');
--   -- debe esperar el FOR UPDATE de A.
-- SESSION A: rollback;
-- SESSION B: la llamada continúa; verificar respuesta OK y luego rollback;
-- Verificación final read-only: la fila debe conservar exactamente su estado previo.
