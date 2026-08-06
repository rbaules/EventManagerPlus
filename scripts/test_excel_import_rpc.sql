-- EventPlus 7C: guion MANUAL. La migracion no se aplica desde este archivo.
-- NO ejecutar en produccion. Requiere usuarios Auth y eventos descartables.
-- Reemplace todos los marcadores <...> antes de ejecutar bloques de escritura.

-- ============================================================================
-- A. CONSULTAS SEGURAS DE VERIFICACION (solo lectura)
-- ============================================================================
SELECT p.oid::regprocedure AS firma,
       pg_get_userbyid(p.proowner) AS propietario,
       p.prosecdef AS security_definer,
       p.proconfig AS configuracion,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS execute_authenticated,
       has_function_privilege('anon', p.oid, 'EXECUTE') AS execute_anon,
       coalesce((SELECT bool_or(a.privilege_type = 'EXECUTE')
                 FROM pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) a
                 WHERE a.grantee = 0), false) AS execute_public
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.oid = 'public.evp_importar_evento_desde_json(integer,integer,jsonb,text)'::regprocedure;
-- Esperado: firma exacta, propietario controlado, security_definer=true,
-- configuracion={search_path=pg_catalog}, authenticated=true, anon/public=false.

-- Antes y despues de CADA caso de escritura, inspeccione el evento descartable:
SELECT
  (SELECT count(*) FROM public.evp_mes_mesa
   WHERE mes_cuenta_id=<CUENTA> AND mes_evento_id=<EVENTO>) AS mesas,
  (SELECT count(*) FROM public.evp_inv_invitacion
   WHERE inv_cuenta_id=<CUENTA> AND inv_evento_id=<EVENTO>) AS invitaciones,
  (SELECT count(*) FROM public.evp_ivt_invitado
   WHERE ivt_cuenta_id=<CUENTA> AND ivt_evento_id=<EVENTO>) AS invitados;

-- ============================================================================
-- B. CASOS QUE ESCRIBEN DATOS: SOLO EVENTOS DESCARTABLES
-- ============================================================================
-- Payload base esperado: 2 mesas / 2 invitaciones / 4 invitados.
-- Para simular auth.uid() en SQL Editor use una transaccion y set_config local.
BEGIN;
SELECT set_config('request.jwt.claim.sub', '<AUTH_UUID_MASTER_O_ADMIN>', true);
SELECT public.evp_importar_evento_desde_json(<CUENTA>, <EVENTO>, $json$
{"version":1,"mesas":[{"codigo_externo":"M-01","nombre":"Mesa Uno"},{"codigo_externo":"M-02","nombre":"Mesa Dos"}],"invitaciones":[{"codigo_externo":"INV-001","destinatario":"Familia Uno","puestos_reservados":2,"invitados":[{"orden":1,"nombre":"Invitado Uno","telefono":"06000001","email":"uno@example.com","es_principal":true,"mesa_codigo":"M-01"},{"orden":2,"nombre":"Invitado Dos","telefono":null,"email":null,"es_principal":false,"mesa_codigo":"M-01"}]},{"codigo_externo":"INV-002","destinatario":"Familia Dos","puestos_reservados":2,"invitados":[{"orden":1,"nombre":"Invitado Tres","telefono":null,"email":null,"es_principal":true,"mesa_codigo":"M-02"},{"orden":2,"nombre":"Invitado Cuatro","telefono":null,"email":null,"es_principal":false,"mesa_codigo":null}]}]}
$json$::jsonb, repeat('a',64));
-- Verifique aqui 2/2/4 y los flags/principales/puestos antes de ROLLBACK.
SELECT count(*) AS mesas FROM public.evp_mes_mesa WHERE mes_cuenta_id=<CUENTA> AND mes_evento_id=<EVENTO>;
SELECT count(*) AS invitaciones FROM public.evp_inv_invitacion WHERE inv_cuenta_id=<CUENTA> AND inv_evento_id=<EVENTO>;
SELECT count(*) AS invitados FROM public.evp_ivt_invitado WHERE ivt_cuenta_id=<CUENTA> AND ivt_evento_id=<EVENTO>;
ROLLBACK;

-- Prueba atomica de rollback 0/0/0:
-- 1) confirme 0/0/0 con la consulta segura de A;
-- 2) copie el bloque base, cambie el ultimo mesa_codigo por "NO-EXISTE";
-- 3) ejecute hasta la RPC: debe devolver INVALID_TABLE_REFERENCE;
-- 4) ejecute ROLLBACK (la transaccion queda abortada por la excepcion);
-- 5) ejecute fuera de esa transaccion la consulta segura de A: debe dar 0/0/0.

-- Prueba de roles (un evento descartable vacio por caso):
-- Master activo -> OK aun sin evp_uev_usuario_evento.
-- Administrador con evp_ucu_usuario_cuenta Activo/Administrador -> OK para
-- cualquier evento de esa cuenta, sin evp_uev_usuario_evento.
-- Operador y Consulta, tengan o no asignacion de evento -> IMPORT_FORBIDDEN.
-- Usuario/cuenta inactivo o relacion ucu inactiva -> IMPORT_FORBIDDEN.

-- Prueba de evento no vacio:
-- inserte previamente UNA mesa, invitacion o invitado (tambien estado Inactivo)
-- en un evento descartable y llame la RPC: debe devolver EVENT_NOT_EMPTY sin
-- agregar filas. Repita por cada una de las tres tablas.

-- Prueba de reintento:
-- ejecute el payload base con COMMIT en un evento descartable; repita la misma
-- llamada: debe devolver EVENT_NOT_EMPTY y conservar exactamente 2/2/4.

-- Casos adicionales, cada uno en evento vacio y transaccion propia:
-- evento En_proceso -> EVENT_NOT_PRE_EVENT; evento inactivo -> EVENT_NOT_ACTIVE.
-- version/arrays/tipos/hash invalido -> INVALID_PAYLOAD.
-- cero o dos principales; puestos distintos del numero de invitados -> INVALID_PAYLOAD.
-- mesa repetida por codigo o nombre normalizado -> INVALID_PAYLOAD.
-- nombre de mesa/invitado que normalice a vacio -> INVALID_PAYLOAD.
-- invitado repetido por nombre normalizado -> DUPLICATE_GUEST.

-- ============================================================================
-- C. CONCURRENCIA EXACTA EN DOS SESIONES (mismo evento descartable vacio)
-- ============================================================================
-- SESION A:
--   BEGIN;
--   SELECT pg_catalog.pg_advisory_xact_lock(<CUENTA>, <EVENTO>);
--   -- deje abierta esta transaccion.
-- SESION B, mientras A sigue abierta:
--   BEGIN;
--   SELECT set_config('request.jwt.claim.sub','<AUTH_UUID_MASTER_O_ADMIN>',true);
--   SELECT public.evp_importar_evento_desde_json(<CUENTA>,<EVENTO>,
--          '<PAYLOAD_BASE>'::jsonb, repeat('a',64));
--   -- esperado: CONCURRENT_IMPORT; luego ROLLBACK.
-- SESION A:
--   ROLLBACK;
-- Luego repita la RPC en B: debe completar. Una vez importado, otro intento
-- debe devolver EVENT_NOT_EMPTY. Use ROLLBACK final si desea conservar 0/0/0.

-- ============================================================================
-- D. ROLLBACK DE LA MIGRACION (CAMBIA EL ESQUEMA; entorno controlado solamente)
-- ============================================================================
-- Ejecute supabase/migrations/202608040001_excel_import_rpc_rollback.sql dos
-- veces. Ambas deben terminar sin error. Luego la consulta de A debe retornar
-- cero filas (funcion ausente). Para continuar pruebas, reaplique manualmente la
-- migracion en el entorno descartable; nunca desde este guion ni en produccion.
