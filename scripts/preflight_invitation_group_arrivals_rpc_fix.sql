-- QR-2B hotfix preflight: READ-ONLY. No modifica objetos ni datos.
DO $check$
DECLARE v_read oid:=pg_catalog.to_regprocedure('public.evp_oper_obtener_grupo_invitacion(integer,integer,integer)'); v_write oid:=pg_catalog.to_regprocedure('public.evp_oper_confirmar_llegadas_invitacion(integer,integer,integer,integer[])');
BEGIN
 IF v_read IS NULL OR v_write IS NULL THEN RAISE EXCEPTION '202609270003 no esta instalada: faltan firmas QR-2B'; END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=v_read AND p.prorettype='jsonb'::regtype AND p.prosecdef)
    OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=v_write AND p.prorettype='jsonb'::regtype AND p.prosecdef) THEN RAISE EXCEPTION 'Metadatos QR-2B incompatibles'; END IF;
 IF pg_catalog.to_regclass('public.evp_ivt_invitado') IS NULL OR pg_catalog.to_regclass('public.evp_inv_invitacion') IS NULL OR pg_catalog.to_regclass('public.evp_eve_evento') IS NULL THEN RAISE EXCEPTION 'Dependencias QR-2B faltantes'; END IF;
END $check$;
SELECT p.oid::regprocedure AS firma,
       position('pg_catalog.coalesce' IN pg_catalog.pg_get_functiondef(p.oid))>0 AS coalesce_calificado_defectuoso,
       position('jsonb_agg' IN pg_catalog.pg_get_functiondef(p.oid))>0 AS usa_jsonb_agg,
       position('array_agg' IN pg_catalog.pg_get_functiondef(p.oid))>0 AS usa_array_agg,
       position('FOR UPDATE' IN pg_catalog.pg_get_functiondef(p.oid))>0 AS usa_for_update
FROM pg_catalog.pg_proc p
WHERE p.oid IN (pg_catalog.to_regprocedure('public.evp_oper_obtener_grupo_invitacion(integer,integer,integer)'),pg_catalog.to_regprocedure('public.evp_oper_confirmar_llegadas_invitacion(integer,integer,integer,integer[])'))
ORDER BY p.oid::regprocedure::text;
SELECT 'SUMMARY' AS check,'PASS' AS result,'READY: 202609270004 aun no se aplica; revisar patrones antes del hotfix' AS detail;
