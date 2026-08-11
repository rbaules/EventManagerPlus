-- Prueba local/controlada de Tarea 8C. NO ejecutar automáticamente en remoto.
-- Ejecutar después de aplicar la migración en una BD efímera con roles Supabase.
begin;

do $$
declare
  v_signature text;
  v_proc record;
  v_definition text;
begin
  foreach v_signature in array array[
    'public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer)',
    'public.evp_admin_actualizar_usuario(uuid,text,text)',
    'public.evp_admin_cambiar_estado_usuario(uuid,text)',
    'public.evp_admin_cambiar_master(uuid,boolean)'
  ] loop
    select p.oid, p.prosecdef, p.proconfig, r.rolname as owner_name
      into strict v_proc
      from pg_catalog.pg_proc p
      join pg_catalog.pg_roles r on r.oid=p.proowner
      where p.oid=to_regprocedure(v_signature);
    assert v_proc.prosecdef, v_signature || ' debe ser SECURITY DEFINER';
    assert v_proc.proconfig @> array['search_path=""'], v_signature || ' debe usar search_path vacio';
    assert v_proc.owner_name='postgres', v_signature || ' debe pertenecer a postgres';
    assert has_function_privilege('authenticated', v_signature, 'EXECUTE'), v_signature || ': authenticated sin EXECUTE';
    assert not has_function_privilege('anon', v_signature, 'EXECUTE'), v_signature || ': anon tiene EXECUTE';
    assert not exists (
      select 1 from aclexplode(coalesce((select proacl from pg_catalog.pg_proc where oid=v_proc.oid),
                                        acldefault('f',(select proowner from pg_catalog.pg_proc where oid=v_proc.oid)))) a
      where a.grantee=0 and a.privilege_type='EXECUTE'
    ), v_signature || ': PUBLIC tiene EXECUTE';
  end loop;

  assert not has_function_privilege('authenticated', 'public.evp_admin_actor_es_master()', 'EXECUTE');
  assert not has_function_privilege('authenticated', 'public.evp_admin_actor_puede_preregistrar()', 'EXECUTE');

  select pg_get_functiondef('public.evp_admin_cambiar_estado_usuario(uuid,text)'::regprocedure) into v_definition;
  assert position('pg_advisory_xact_lock(817301)' in v_definition) < position('for update' in lower(v_definition)),
    'cambiar_estado debe tomar advisory lock antes de FOR UPDATE';
  select pg_get_functiondef('public.evp_admin_cambiar_master(uuid,boolean)'::regprocedure) into v_definition;
  assert position('pg_advisory_xact_lock(817301)' in v_definition) < position('for update' in lower(v_definition)),
    'cambiar_master debe tomar advisory lock antes de FOR UPDATE';
end $$;

-- CORRECCION INCREMENTAL 8C (despues de aplicar 202608080001)
do $$
declare
  v_definition text;
  v_usr_insert integer;
  v_cuenta_insert integer;
  v_evento_insert integer;
  v_defaults_update integer;
  v_compact text;
begin
  assert exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='evp_usr_usuario' and column_name='usr_creado_por'
  ), 'falta trazabilidad usr_creado_por';
  select pg_get_functiondef('public.evp_admin_crear_usuario(text,text,boolean,integer,text,integer,integer)'::regprocedure) into v_definition;
  assert position('usr_creado_por' in v_definition)>0, 'crear no registra creador';
  assert position('usr_cuenta_id_default' in v_definition)>0, 'crear no gestiona cuenta default';
  assert position('usr_evento_id_default' in v_definition)>0, 'crear no gestiona evento default';
  assert position('insert into public.evp_uev_usuario_evento' in lower(v_definition))>0, 'default Operador/Consulta sin asignacion atomica';
  v_definition := lower(v_definition);
  v_compact := regexp_replace(v_definition, '\s+', '', 'g');
  v_usr_insert := position('insert into public.evp_usr_usuario' in v_definition);
  v_cuenta_insert := position('insert into public.evp_ucu_usuario_cuenta' in v_definition);
  v_evento_insert := position('insert into public.evp_uev_usuario_evento' in v_definition);
  v_defaults_update := position('update public.evp_usr_usuario' in substring(v_definition from v_evento_insert)) + v_evento_insert - 1;
  assert v_usr_insert < v_cuenta_insert and v_cuenta_insert < v_evento_insert
         and v_evento_insert < v_defaults_update,
    'orden requerido: usuario -> cuenta -> evento -> defaults';
  assert position('null,null,v_actor_id' in v_compact)>0,
    'el usuario debe insertarse con defaults NULL';
  assert position('setusr_cuenta_id_default=p_cuenta_default_id' in v_compact)>0
         and position('usr_evento_id_default=p_evento_default_id' in v_compact)>0,
    'falta UPDATE final de defaults explicitos';
  assert position('coalesce(p_cuenta_default_id,p_cuenta_id)' in v_definition)=0,
    'la respuesta no debe confundir cuenta inicial con cuenta default';
  assert position('returningusr_cuenta_id_default,usr_evento_id_default' in v_compact)>0,
    'la respuesta debe usar los defaults realmente persistidos';
  select pg_get_functiondef('public.evp_admin_actualizar_usuario(uuid,text,text)'::regprocedure) into v_definition;
  assert position('usr_creado_por' in v_definition)>0 and position('USER_EDIT_FORBIDDEN' in v_definition)>0,
    'actualizar no valida autor real';
end $$;

rollback;

-- PRUEBAS FUNCIONALES EXACTAS (BD efímera)
-- 1. Crear fixtures: dos Masters Activos con UUID Auth, un Administrador Activo
--    vinculado como Administrador a una cuenta Activa, un Operador y un Consulta.
-- 2. Antes de cada llamada, simular al actor dentro de la misma transacción:
--      select set_config('request.jwt.claim.sub','<AUTH_UUID_ACTOR>',true);
-- 3. La llamada debe abortar con el código indicado:
--
-- Auto-inactivación (Master actor):
--   select public.evp_admin_cambiar_estado_usuario('<ID_MASTER_ACTOR>','Inactivo');
--   => SELF_DEACTIVATION_FORBIDDEN
--
-- Último Master: dejar exactamente un Master Activo y, actuando como ese Master,
-- inactivar su perfil o retirar Master. La primera acción devuelve
-- SELF_DEACTIVATION_FORBIDDEN; para comprobar LAST_MASTER, actuar con otro Master
-- autenticado temporalmente y retirar/inactivar al único Master Activo objetivo:
--   select public.evp_admin_cambiar_master('<ID_UNICO_MASTER_ACTIVO>',false);
--   => LAST_MASTER
--
-- Administrador crea Operador/Consulta en su cuenta Activa (repetir por rol):
--   select public.evp_admin_crear_usuario('Prueba','admin-ok@example.test',false,1,'Operador');
--   => perfil Preregistrado, relacion Activa, visible para el Admin.
-- Administrador intenta crear Master:
--   select public.evp_admin_crear_usuario('Prueba','admin-master@example.test',true,1,'Operador');
--   => USER_ADMIN_FORBIDDEN
--
-- Operador y Consulta (repetir con el UUID Auth de cada actor):
--   select public.evp_admin_crear_usuario('Prueba','sin-permiso@example.test',false,1,'Operador');
--   => USER_ADMIN_FORBIDDEN
--
-- Preregistrado sin Auth -> Activo (actuando como Master):
--   select public.evp_admin_cambiar_estado_usuario('<ID_PREREGISTRADO_SIN_AUTH>','Activo');
--   => AUTH_REQUIRED
--
-- Correo duplicado normalizado (actuando como Master):
--   select public.evp_admin_crear_usuario('Uno','Duplicado@Example.Test',false,null,null);
--   select public.evp_admin_crear_usuario('Dos','  duplicado@example.test  ',false,null,null);
--   => segunda llamada USER_EMAIL_EXISTS
-- Admin sin cuenta => ACCOUNT_REQUIRED; sin rol => ROLE_REQUIRED; rol Administrador
-- => INVALID_ACCOUNT_ROLE; cuenta ajena => ACCOUNT_FORBIDDEN.
-- Forzar una violacion al insertar evp_ucu_usuario_cuenta y comprobar que tampoco
-- queda el perfil: la funcion completa es una unica transaccion atomica.
-- Master sin cuenta:
--   select public.evp_admin_crear_usuario('Master crea','master-sin-cuenta@example.test',false,null,null);
-- Master con cuenta y rol valido tambien se admite en la firma server-side.
--
-- Casos incrementales de defaults y autoria (cada uno dentro de BEGIN/ROLLBACK):
-- 1. Admin crea Operador con cuenta inicial y defaults NULL: la relacion queda
--    Activa, ambos defaults terminan NULL y el JSON devuelve cuenta_default_id null.
-- 2. Master crea Operador con cuenta/evento default: existen ambas relaciones y
--    los dos defaults coinciden con el UPDATE ... RETURNING y con el JSON.
-- 3. Master crea Administrador con evento default: no existe asignacion
--    evp_uev redundante; las preferencias quedan persistidas.
-- 4. Master crea Master con defaults: no existen relaciones redundantes y las
--    preferencias quedan persistidas por su acceso global.
-- 5. En todos los casos usr_creado_por coincide con el usuario interno resuelto
--    desde el UUID Auth del actor.
-- 6. Provocar el fallo del UPDATE final (por ejemplo, fixture efimero que haga
--    fallar su FK/CHECK) y capturar la excepcion fuera de la llamada. Tras ella,
--    contar por el correo/UUID retornable: deben quedar cero perfiles, cero
--    relaciones de cuenta y cero asignaciones de evento. Esto demuestra rollback
--    de la unica sentencia/RPC, no una compensacion manual.
-- 7. Admin A edita su usuario no Master mientras comparten cuenta Activa bajo
--    una relacion Administrador/Activo: OK. Admin B: USER_EDIT_FORBIDDEN.
--    Poner usr_creado_por NULL: cualquier Admin recibe USER_EDIT_FORBIDDEN y
--    Master puede editarlo.
--
-- Encerrar cada caso en BEGIN/ROLLBACK. Confirmar el código desde SQLSTATE P0001
-- y SQLERRM en un bloque DO si se automatiza.

-- ROLLBACK IDEMPOTENTE (BD efímera separada)
-- Ejecutar literalmente, dos veces consecutivas:
--   psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/202608060001_user_admin_profile_rpc_rollback.sql
--   psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/202608060001_user_admin_profile_rpc_rollback.sql
-- Ambas ejecuciones deben terminar con código 0. Después, las seis funciones
-- deben devolver NULL mediante to_regprocedure(...).

-- CONCURRENCIA EN DOS SESIONES (BD efímera, dos Masters activos M1/M2)
-- Sesión A:
--   begin;
--   select set_config('request.jwt.claim.sub','<AUTH_UUID_M1>',true);
--   select public.evp_admin_cambiar_master('<ID_M2>',false);
--   -- mantener la transacción abierta antes del COMMIT.
-- Sesión B, mientras A sigue abierta:
--   begin;
--   select set_config('request.jwt.claim.sub','<AUTH_UUID_M2>',true);
--   select public.evp_admin_cambiar_estado_usuario('<ID_M1>','Inactivo');
--   -- debe esperar el mismo advisory lock 817301, nunca producir deadlock.
-- Sesión A: commit;
-- Sesión B: debe finalizar controladamente (normalmente LAST_MASTER, según fixture),
--           luego rollback;
-- Verificar pg_locks durante la espera: ambas operaciones usan advisory lock antes
-- de cualquier SELECT objetivo FOR UPDATE.
