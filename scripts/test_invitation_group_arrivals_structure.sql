-- QR-2B structural verification: READ-ONLY.
DO $check$
DECLARE f oid; s text;
BEGIN
 FOREACH s IN ARRAY ARRAY['public.evp_oper_obtener_grupo_invitacion(integer,integer,integer)','public.evp_oper_confirmar_llegadas_invitacion(integer,integer,integer,integer[])'] LOOP
  f:=pg_catalog.to_regprocedure(s); IF f IS NULL THEN RAISE EXCEPTION 'Falta %',s; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE p.oid=f AND p.prokind='f' AND p.prorettype='jsonb'::regtype AND p.prosecdef AND r.rolname='postgres' AND EXISTS(SELECT 1 FROM pg_catalog.unnest(p.proconfig)c(x) WHERE pg_catalog.split_part(x,'=',1)='search_path' AND pg_catalog.btrim(pg_catalog.split_part(x,'=',2),'"')='')) THEN RAISE EXCEPTION 'Metadatos inseguros: %',s; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.oid=f AND p.proargnames=CASE WHEN s LIKE '%integer[])' THEN ARRAY['p_cuenta_id','p_evento_id','p_invitacion_id','p_invitado_ids'] ELSE ARRAY['p_cuenta_id','p_evento_id','p_invitacion_id'] END) THEN RAISE EXCEPTION 'Argumentos incorrectos: %',s; END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc p CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a WHERE p.oid=f AND a.grantee=0 AND a.privilege_type='EXECUTE') OR pg_catalog.has_function_privilege('anon',f,'EXECUTE') OR NOT pg_catalog.has_function_privilege('authenticated',f,'EXECUTE') THEN RAISE EXCEPTION 'Privilegios incorrectos: %',s; END IF;
 END LOOP;
 IF pg_catalog.to_regprocedure('public.evp_oper_resolver_invitacion_qr(integer,integer,text)') IS NULL THEN RAISE EXCEPTION 'QR-2A fue alterado'; END IF;
END $check$;
SELECT 'PASS' AS invitation_group_arrivals_structure;
