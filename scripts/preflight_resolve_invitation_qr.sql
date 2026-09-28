-- QR-2A preflight READ-ONLY, antes de aplicar 202609270002.
WITH checks(nombre, ok, detalle) AS (
 SELECT 'qr_table', pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') IS NOT NULL, 'QR-1B'
 UNION ALL SELECT 'qr_admin_rpc', pg_catalog.to_regprocedure('public.evp_admin_obtener_qr_invitacion(integer,integer,integer)') IS NOT NULL, 'QR-1C-B1'
 UNION ALL SELECT 'resolver_signature_free', pg_catalog.to_regprocedure('public.evp_oper_resolver_invitacion_qr(integer,integer,text)') IS NULL, 'firma QR-2A libre'
 UNION ALL SELECT 'required_tables', (SELECT pg_catalog.count(*)=6 FROM (VALUES ('public.evp_cta_cuenta'),('public.evp_eve_evento'),('public.evp_inv_invitacion'),('public.evp_ivt_invitado'),('public.evp_mes_mesa'),('public.evp_uev_usuario_evento')) x(n) WHERE pg_catalog.to_regclass(n) IS NOT NULL), 'dependencias'
 UNION ALL SELECT 'qr_rls', EXISTS (SELECT 1 FROM pg_catalog.pg_class WHERE oid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND relrowsecurity), 'RLS QR'
 UNION ALL SELECT 'qr_unique', EXISTS (SELECT 1 FROM pg_catalog.pg_constraint WHERE conrelid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND conname='uq_evp_iqr_cuenta_evento_codigo'), 'UNIQUE contexto+codigo'
), report AS (SELECT nombre,ok,detalle,1 orden FROM checks UNION ALL SELECT 'SUMMARY',pg_catalog.bool_and(ok),CASE WHEN pg_catalog.bool_and(ok) THEN 'READY' ELSE 'NOT READY' END,2 FROM checks)
SELECT nombre,CASE WHEN ok THEN 'PASS' ELSE 'FAIL' END estado,detalle FROM report ORDER BY orden,nombre;
