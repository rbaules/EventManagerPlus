-- QR-2B preflight: READ-ONLY. Ejecutar antes de 202609270003.
DO $preflight$
BEGIN
  IF pg_catalog.to_regclass('public.evp_cta_cuenta') IS NULL
     OR pg_catalog.to_regclass('public.evp_eve_evento') IS NULL
     OR pg_catalog.to_regclass('public.evp_inv_invitacion') IS NULL
     OR pg_catalog.to_regclass('public.evp_ivt_invitado') IS NULL
     OR pg_catalog.to_regclass('public.evp_usr_usuario') IS NULL
     OR pg_catalog.to_regclass('public.evp_ucu_usuario_cuenta') IS NULL
     OR pg_catalog.to_regclass('public.evp_uev_usuario_evento') IS NULL THEN
    RAISE EXCEPTION 'Faltan tablas requeridas para llegadas por invitacion';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid='public.evp_ivt_invitado'::regclass
       AND a.attname IN ('ivt_llegada_confirmada','ivt_fecha_hora_conf_llegada','ivt_usuario_conf_llegada')
       AND a.attisdropped) OR (SELECT count(*) FROM pg_catalog.pg_attribute a WHERE a.attrelid='public.evp_ivt_invitado'::regclass
       AND a.attname IN ('ivt_llegada_confirmada','ivt_fecha_hora_conf_llegada','ivt_usuario_conf_llegada') AND NOT a.attisdropped) <> 3 THEN
    RAISE EXCEPTION 'Faltan campos de llegada';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute WHERE attrelid='public.evp_ivt_invitado'::regclass AND attname='ivt_llegada_confirmada' AND atttypid='boolean'::regtype)
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute WHERE attrelid='public.evp_ivt_invitado'::regclass AND attname='ivt_fecha_hora_conf_llegada' AND atttypid='timestamp with time zone'::regtype)
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute WHERE attrelid='public.evp_ivt_invitado'::regclass AND attname='ivt_usuario_conf_llegada' AND atttypid='uuid'::regtype) THEN
    RAISE EXCEPTION 'Tipos de llegada incompatibles';
  END IF;
  IF pg_catalog.to_regprocedure('public.evp_oper_obtener_grupo_invitacion(integer,integer,integer)') IS NOT NULL
     OR pg_catalog.to_regprocedure('public.evp_oper_confirmar_llegadas_invitacion(integer,integer,integer,integer[])') IS NOT NULL THEN
    RAISE EXCEPTION 'Las firmas QR-2B ya existen';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('anon','authenticated','postgres')) THEN RAISE EXCEPTION 'Faltan roles requeridos'; END IF;
END $preflight$;
SELECT c.relname AS tabla, c.relrowsecurity AS rls_habilitado, c.relforcerowsecurity AS force_rls,
       (SELECT count(*) FROM pg_catalog.pg_policy p WHERE p.polrelid=c.oid AND p.polcmd IN ('u','*')) AS politicas_update,
       pg_catalog.has_table_privilege('authenticated',c.oid,'UPDATE') AS authenticated_tiene_update_sql
FROM pg_catalog.pg_class c WHERE c.oid='public.evp_ivt_invitado'::regclass;
SELECT 'SUMMARY' AS check, 'PASS' AS result, 'READY' AS detail;
