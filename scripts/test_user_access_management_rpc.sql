-- Test PostgreSQL de administración UCU/UEV. Ejecutar manualmente después de 202608110003.
-- A) ACL read-only; B) funcional autocontenida con ROLLBACK; C) concurrencia separada.
begin;
-- Para una ejecución funcional autocontenida, descomentar SOLO la línea siguiente:
-- do $$ begin perform set_config('eventplus.run_uam_functional','on',true); end $$;

create temporary table uam_test_results(
  orden integer primary key,
  prueba text not null,
  resultado text not null,
  detalle text not null
) on commit drop;

-- A. READ-ONLY
do $$ declare signature text; p oid; owner_name text; config text[]; begin
  foreach signature in array array[
    'public.evp_admin_agregar_cuenta_usuario(uuid,integer,text,integer)',
    'public.evp_admin_agregar_evento_usuario(uuid,integer,integer)',
    'public.evp_admin_cambiar_estado_evento_usuario(uuid,integer,integer,text)',
    'public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer)',
    'public.evp_admin_cambiar_estado_cuenta(uuid,integer,text)',
    'public.evp_admin_buscar_usuario_para_cuenta(integer,text)'
  ] loop
    p:=to_regprocedure(signature); assert p is not null, signature||' no existe';
    select r.rolname,x.proconfig into owner_name,config from pg_proc x join pg_roles r on r.oid=x.proowner where x.oid=p;
    assert (select prosecdef from pg_proc where oid=p), signature||' no es SECURITY DEFINER';
    assert config @> array['search_path=""'], signature||' no fija search_path vacío';
    assert owner_name=current_user or owner_name in ('postgres','supabase_admin'), signature||' propietario no confiable';
    assert not exists(select 1 from aclexplode(coalesce((select proacl from pg_proc where oid=p),acldefault('f',(select proowner from pg_proc where oid=p)))) a where a.grantee=0 and a.privilege_type='EXECUTE'), signature||' permite PUBLIC';
    assert not has_function_privilege('anon',signature,'EXECUTE'), signature||' permite anon';
    assert has_function_privilege('authenticated',signature,'EXECUTE'), signature||' bloquea authenticated';
  end loop;
  foreach signature in array array[
    'public.evp_priv_8d_cambiar_rol_cuenta(uuid,integer,text,integer)',
    'public.evp_priv_8d_cambiar_estado_cuenta(uuid,integer,text)',
    'public.evp_priv_8d_aplicar_transicion_rol(uuid,integer,text,text,integer,boolean)',
    'public.evp_priv_limpiar_defaults(uuid)'
  ] loop
    p:=to_regprocedure(signature); assert p is not null, signature||' no existe';
    select r.rolname,x.proconfig into owner_name,config from pg_proc x join pg_roles r on r.oid=x.proowner where x.oid=p;
    assert (select prosecdef from pg_proc where oid=p), signature||' no es SECURITY DEFINER';
    assert config @> array['search_path=""'], signature||' no fija search_path vacío';
    assert owner_name=current_user or owner_name in ('postgres','supabase_admin'), signature||' propietario no confiable';
    assert not exists(select 1 from aclexplode(coalesce((select proacl from pg_proc where oid=p),acldefault('f',(select proowner from pg_proc where oid=p)))) a where a.grantee=0 and a.privilege_type='EXECUTE');
    assert not has_function_privilege('anon',signature,'EXECUTE');
    assert not has_function_privilege('authenticated',signature,'EXECUTE');
  end loop;
end $$;

-- B. FUNCIONAL AUTOCONTENIDA. Codex NO ejecutó esta sección.
-- La activación sin result set está preparada al inicio mediante DO/PERFORM.
do $$
declare
  master_id constant uuid := 'c14208de-e66d-4f0b-864c-15d6720734d9';
  master_auth constant uuid := '397bc597-6e61-4447-a222-dcdb55051f7b';
  admin_id constant uuid := 'a73f0cf1-e655-4126-bd4e-1020278af9c9';
  admin_auth constant uuid := 'a3b47ae0-2824-4763-941c-4b38d9785994';
  cuenta_a constant integer := 2; cuenta_b constant integer := 3;
  evento_a1 constant integer := 1; evento_a2 constant integer := 2;
  u_multi constant uuid := '8d000001-0000-4000-8000-000000000001';
  u_admin_same constant uuid := '8d000002-0000-4000-8000-000000000002';
  u_t1 constant uuid := '8d000011-0000-4000-8000-000000000011';
  u_t2 constant uuid := '8d000012-0000-4000-8000-000000000012';
  u_t3 constant uuid := '8d000013-0000-4000-8000-000000000013';
  u_t4 constant uuid := '8d000014-0000-4000-8000-000000000014';
  u_t5 constant uuid := '8d000015-0000-4000-8000-000000000015';
  u_t6 constant uuid := '8d000016-0000-4000-8000-000000000016';
  synthetic_ids uuid[]; rejected boolean; error_message text;
  master_modificado timestamptz; admin_modificado timestamptz;
begin
  if coalesce(current_setting('eventplus.run_uam_functional',true),'off')<>'on' then
    raise notice 'Funcional UAM omitida: run_uam_functional no está en on'; return;
  end if;
  synthetic_ids:=array[u_multi,u_admin_same,u_t1,u_t2,u_t3,u_t4,u_t5,u_t6];

  -- Validaciones previas, antes de crear fixtures.
  assert exists(select 1 from public.evp_usr_usuario where usr_usuario_id=master_id and usr_usuario_auth_uuid=master_auth and usr_es_usuario_master and usr_estado='Activo'), 'PRECONDITION MASTER';
  assert exists(select 1 from public.evp_usr_usuario where usr_usuario_id=admin_id and usr_usuario_auth_uuid=admin_auth and not usr_es_usuario_master and usr_estado='Activo'), 'PRECONDITION ADMIN_A';
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=admin_id and ucu_cuenta_id=cuenta_a and ucu_rol='Administrador' and ucu_estado='Activo'), 'PRECONDITION UCU ADMIN_A';
  assert exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=cuenta_a and cta_estado='Activo'), 'PRECONDITION CUENTA_A';
  assert exists(select 1 from public.evp_cta_cuenta where cta_cuenta_id=cuenta_b and cta_estado='Activo'), 'PRECONDITION CUENTA_B';
  assert exists(select 1 from public.evp_eve_evento where eve_cuenta_id=cuenta_a and eve_evento_id=evento_a1 and eve_estado='Activo'), 'PRECONDITION EVENTO_A1';
  assert exists(select 1 from public.evp_eve_evento where eve_cuenta_id=cuenta_a and eve_evento_id=evento_a2 and eve_estado='Activo'), 'PRECONDITION EVENTO_A2';
  assert not exists(select 1 from public.evp_usr_usuario where usr_usuario_id=any(synthetic_ids)), 'COLISIÓN UUID SINTÉTICO';
  select usr_modificado into master_modificado from public.evp_usr_usuario where usr_usuario_id=master_id;
  select usr_modificado into admin_modificado from public.evp_usr_usuario where usr_usuario_id=admin_id;

  -- Perfiles EventPlus sintéticos; no se inserta ni modifica auth.users.
  insert into public.evp_usr_usuario(usr_usuario_id,usr_nombre_usuario,usr_nombre_usuario_abrev,usr_usuario_auth_uuid,usr_es_usuario_master,usr_email,usr_cuenta_id_default,usr_evento_id_default,usr_estado) values
    (u_multi,'UAM Test Multi','UAM-MULTI',null,false,'uam-test-multi@eventplus.invalid',null,null,'Preregistrado'),
    (u_admin_same,'UAM Test Admin','UAM-ADMIN',null,false,'uam-test-admin@eventplus.invalid',null,null,'Preregistrado'),
    (u_t1,'UAM Test T1','UAM-T1',null,false,'uam-test-t1@eventplus.invalid',null,null,'Preregistrado'),
    (u_t2,'UAM Test T2','UAM-T2',null,false,'uam-test-t2@eventplus.invalid',null,null,'Preregistrado'),
    (u_t3,'UAM Test T3','UAM-T3',null,false,'uam-test-t3@eventplus.invalid',null,null,'Preregistrado'),
    (u_t4,'UAM Test T4','UAM-T4',null,false,'uam-test-t4@eventplus.invalid',null,null,'Preregistrado'),
    (u_t5,'UAM Test T5','UAM-T5',null,false,'uam-test-t5@eventplus.invalid',null,null,'Preregistrado'),
    (u_t6,'UAM Test T6','UAM-T6',null,false,'uam-test-t6@eventplus.invalid',null,null,'Preregistrado');

  -- MULTI y SAME_ACCOUNT_ADMIN.
  insert into public.evp_ucu_usuario_cuenta values(cuenta_b,u_multi,'Administrador','Activo'),(cuenta_a,u_admin_same,'Administrador','Activo');
  insert into public.evp_uev_usuario_evento values(cuenta_a,evento_a1,u_admin_same,'Activo');
  perform set_config('request.jwt.claim.sub',admin_auth::text,true);
  assert auth.uid()=admin_auth, 'AUTH ADMIN_A';
  perform public.evp_admin_agregar_cuenta_usuario(u_multi,cuenta_a,'Operador',evento_a1);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=u_multi and ucu_cuenta_id=cuenta_a and ucu_rol='Operador' and ucu_estado='Activo'), 'MULTI UCU A';
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_usuario_id=u_multi and ucu_cuenta_id=cuenta_b and ucu_rol='Administrador' and ucu_estado='Activo'), 'MULTI UCU B';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_usuario_id=u_multi and uev_cuenta_id=cuenta_a and uev_evento_id=evento_a1 and uev_estado='Activo'), 'MULTI UEV A1';
  insert into uam_test_results values(10,'MULTI','PASS','Admin A agregó Operador en Cuenta A; Administrador en Cuenta B quedó intacto');
  raise notice 'PASS MULTI';

  rejected:=false; begin perform public.evp_admin_cambiar_rol_cuenta(u_admin_same,cuenta_a,'Operador',evento_a1); exception when sqlstate 'P0001' then get stacked diagnostics error_message=message_text; rejected:=error_message='ROLE_CHANGE_FORBIDDEN'; end; assert rejected, 'SAME cambiar rol';
  rejected:=false; begin perform public.evp_admin_cambiar_estado_cuenta(u_admin_same,cuenta_a,'Inactivo'); exception when sqlstate 'P0001' then get stacked diagnostics error_message=message_text; rejected:=error_message='ACCOUNT_RELATION_FORBIDDEN'; end; assert rejected, 'SAME estado UCU';
  rejected:=false; begin perform public.evp_admin_agregar_cuenta_usuario(u_admin_same,cuenta_a,'Operador',evento_a1); exception when sqlstate 'P0001' then get stacked diagnostics error_message=message_text; rejected:=error_message='TARGET_ACCOUNT_ADMIN_FORBIDDEN'; end; assert rejected, 'SAME agregar UCU';
  rejected:=false; begin perform public.evp_admin_agregar_evento_usuario(u_admin_same,cuenta_a,evento_a2); exception when sqlstate 'P0001' then get stacked diagnostics error_message=message_text; rejected:=error_message='EVENT_RELATION_FORBIDDEN'; end; assert rejected, 'SAME agregar UEV';
  rejected:=false; begin perform public.evp_admin_cambiar_estado_evento_usuario(u_admin_same,cuenta_a,evento_a1,'Inactivo'); exception when sqlstate 'P0001' then get stacked diagnostics error_message=message_text; rejected:=error_message='EVENT_RELATION_FORBIDDEN'; end; assert rejected, 'SAME estado UEV';
  insert into uam_test_results values(20,'SAME_ACCOUNT_ADMIN','PASS','Las cinco operaciones administrativas fueron rechazadas');
  raise notice 'PASS SAME_ACCOUNT_ADMIN';

  -- Estados históricos T1-T6; evento_id siempre acompañado por cuenta_id.
  insert into public.evp_ucu_usuario_cuenta values
    (cuenta_a,u_t1,'Operador','Activo'),(cuenta_a,u_t2,'Consulta','Activo'),(cuenta_a,u_t3,'Administrador','Activo'),
    (cuenta_a,u_t4,'Administrador','Activo'),(cuenta_a,u_t5,'Operador','Activo'),(cuenta_a,u_t6,'Consulta','Activo');
  insert into public.evp_uev_usuario_evento values
    (cuenta_a,evento_a1,u_t1,'Activo'),(cuenta_a,evento_a2,u_t1,'Activo'),(cuenta_a,evento_a1,u_t2,'Activo'),(cuenta_a,evento_a2,u_t2,'Activo'),
    (cuenta_a,evento_a1,u_t3,'Activo'),(cuenta_a,evento_a2,u_t3,'Activo'),(cuenta_a,evento_a1,u_t4,'Activo'),(cuenta_a,evento_a2,u_t4,'Activo'),
    (cuenta_a,evento_a1,u_t5,'Activo'),(cuenta_a,evento_a2,u_t5,'Inactivo'),(cuenta_a,evento_a1,u_t6,'Activo'),(cuenta_a,evento_a2,u_t6,'Inactivo');
  update public.evp_usr_usuario set usr_cuenta_id_default=cuenta_a,usr_evento_id_default=evento_a1 where usr_usuario_id in(u_t1,u_t3,u_t4);
  update public.evp_ucu_usuario_cuenta set ucu_estado='Inactivo' where ucu_cuenta_id=cuenta_a and ucu_usuario_id in(u_t1,u_t2,u_t3,u_t4,u_t5,u_t6);

  perform set_config('request.jwt.claim.sub',master_auth::text,true);
  assert auth.uid()=master_auth, 'AUTH MASTER';

  perform public.evp_admin_agregar_cuenta_usuario(u_t1,cuenta_a,'Administrador',null);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t1 and ucu_rol='Administrador' and ucu_estado='Activo'), 'T1 UCU';
  assert not exists(select 1 from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t1 and uev_estado='Activo'), 'T1 UEV';
  assert (select usr_cuenta_id_default=cuenta_a and usr_evento_id_default=evento_a1 from public.evp_usr_usuario where usr_usuario_id=u_t1), 'DEFAULT 3';
  insert into uam_test_results values(30,'T1','PASS','Operador/Inactiva a Administrador; todas las UEV quedaron Inactivas');
  insert into uam_test_results values(100,'DEFAULT_3','PASS','Default A1 permaneció por acceso heredado de Administrador');
  raise notice 'PASS T1'; raise notice 'PASS DEFAULT_3';

  perform public.evp_admin_agregar_cuenta_usuario(u_t2,cuenta_a,'Administrador',null);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t2 and ucu_rol='Administrador' and ucu_estado='Activo'), 'T2 UCU';
  assert not exists(select 1 from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t2 and uev_estado='Activo'), 'T2 UEV';
  insert into uam_test_results values(40,'T2','PASS','Consulta/Inactiva a Administrador; todas las UEV quedaron Inactivas');
  raise notice 'PASS T2';

  perform public.evp_admin_agregar_cuenta_usuario(u_t3,cuenta_a,'Operador',evento_a1);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t3 and ucu_rol='Operador' and ucu_estado='Activo'), 'T3 UCU';
  assert (select count(*) from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t3 and uev_estado='Activo')=1, 'T3 UEV';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_evento_id=evento_a1 and uev_usuario_id=u_t3 and uev_estado='Activo'), 'T3 A1';
  assert (select usr_cuenta_id_default=cuenta_a and usr_evento_id_default=evento_a1 from public.evp_usr_usuario where usr_usuario_id=u_t3), 'DEFAULT 2';
  insert into uam_test_results values(50,'T3','PASS','Administrador/Inactiva a Operador; solo A1 quedó Activa');
  insert into uam_test_results values(90,'DEFAULT_2','PASS','Default A1 permaneció al coincidir con el evento inicial');
  raise notice 'PASS T3'; raise notice 'PASS DEFAULT_2';

  perform public.evp_admin_agregar_cuenta_usuario(u_t4,cuenta_a,'Consulta',evento_a2);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t4 and ucu_rol='Consulta' and ucu_estado='Activo'), 'T4 UCU';
  assert (select count(*) from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t4 and uev_estado='Activo')=1, 'T4 UEV';
  assert exists(select 1 from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_evento_id=evento_a2 and uev_usuario_id=u_t4 and uev_estado='Activo'), 'T4 A2';
  assert (select usr_cuenta_id_default=cuenta_a and usr_evento_id_default is null from public.evp_usr_usuario where usr_usuario_id=u_t4), 'DEFAULT 1';
  insert into uam_test_results values(60,'T4','PASS','Administrador/Inactiva a Consulta; solo A2 quedó Activa');
  insert into uam_test_results values(80,'DEFAULT_1','PASS','Default A1 quedó NULL; no se sustituyó automáticamente por A2');
  raise notice 'PASS T4'; raise notice 'PASS DEFAULT_1';

  perform public.evp_admin_agregar_cuenta_usuario(u_t5,cuenta_a,'Consulta',evento_a2);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t5 and ucu_rol='Consulta' and ucu_estado='Activo'), 'T5 UCU';
  assert (select count(*) from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t5 and uev_estado='Activo')=2, 'T5 UEV';
  insert into uam_test_results values(70,'T5','PASS','Operador/Inactiva a Consulta; A1 se conservó y A2 se activó');
  raise notice 'PASS T5';

  perform public.evp_admin_agregar_cuenta_usuario(u_t6,cuenta_a,'Operador',evento_a2);
  assert exists(select 1 from public.evp_ucu_usuario_cuenta where ucu_cuenta_id=cuenta_a and ucu_usuario_id=u_t6 and ucu_rol='Operador' and ucu_estado='Activo'), 'T6 UCU';
  assert (select count(*) from public.evp_uev_usuario_evento where uev_cuenta_id=cuenta_a and uev_usuario_id=u_t6 and uev_estado='Activo')=2, 'T6 UEV';
  insert into uam_test_results values(75,'T6','PASS','Consulta/Inactiva a Operador; A1 se conservó y A2 se activó');
  raise notice 'PASS T6';
  assert (select usr_modificado is not distinct from master_modificado from public.evp_usr_usuario where usr_usuario_id=master_id), 'ACTOR MASTER MODIFICADO';
  assert (select usr_modificado is not distinct from admin_modificado from public.evp_usr_usuario where usr_usuario_id=admin_id), 'ACTOR ADMIN_A MODIFICADO';
  assert (select count(*) from uam_test_results where resultado='PASS')=11, 'SUMMARY: no hay 11 PASS';
  insert into uam_test_results values(110,'SUMMARY','PASS','11/11 pruebas funcionales superadas');
  raise notice 'PASS FUNCTIONAL UAM; ROLLBACK elimina todos los targets sintéticos';
end $$;

-- Resultado principal: Supabase SQL Editor mostrará estas 12 filas en cuadrícula.
select prueba,resultado,detalle from uam_test_results order by orden;

-- C. CONCURRENCIA: requiere dos sesiones y se ejecutará después.
-- Mantener ambas transacciones bajo ROLLBACK; verificar espera sin deadlock sobre
-- la misma UCU siguiendo locks actor->objetivo->cuenta->UCU->evento->UEV.
rollback;
