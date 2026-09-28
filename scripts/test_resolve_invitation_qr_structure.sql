-- QR-2A estructura READ-ONLY posterior a migracion.
DO $check$
DECLARE f oid := pg_catalog.to_regprocedure('public.evp_oper_resolver_invitacion_qr(integer,integer,text)');
BEGIN
 IF f IS NULL THEN RAISE EXCEPTION 'Falta resolver QR'; END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE p.oid=f AND p.prorettype='pg_catalog.jsonb'::regtype AND p.prosecdef AND r.rolname='postgres' AND p.proargnames=ARRAY['p_cuenta_id','p_evento_id','p_codigo'] AND EXISTS (SELECT 1 FROM pg_catalog.unnest(p.proconfig) c(x) WHERE pg_catalog.split_part(x,'=',1)='search_path' AND pg_catalog.btrim(pg_catalog.split_part(x,'=',2),'"')='')) THEN RAISE EXCEPTION 'Metadatos resolver QR inseguros'; END IF;
 IF pg_catalog.has_function_privilege('anon',f,'EXECUTE') OR NOT pg_catalog.has_function_privilege('authenticated',f,'EXECUTE') THEN RAISE EXCEPTION 'Permisos resolver QR incorrectos'; END IF;
END $check$;
SELECT 'PASS' AS resolve_invitation_qr_structure;
