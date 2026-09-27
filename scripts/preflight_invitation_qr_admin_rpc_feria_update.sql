-- QR-1C-B1 Feria update preflight: READ-ONLY. Ejecutar antes de 202609270001.
WITH expected(signature) AS (
    VALUES ('public.evp_admin_obtener_qr_invitacion(integer,integer,integer)'),
           ('public.evp_admin_crear_qr_invitacion(integer,integer,integer,text)'),
           ('public.evp_admin_regenerar_qr_invitacion(integer,integer,integer,text)')
), checks(check_name, passed, detail) AS (
    SELECT signature, pg_catalog.to_regprocedure(signature) IS NOT NULL, 'RPC instalada'
    FROM expected
    UNION ALL
    SELECT 'rpc_secure_metadata', (
        SELECT pg_catalog.count(*) = 3 FROM expected x JOIN pg_catalog.pg_proc p ON p.oid=pg_catalog.to_regprocedure(x.signature)
        JOIN pg_catalog.pg_roles r ON r.oid=p.proowner WHERE p.prosecdef AND p.prorettype='pg_catalog.jsonb'::regtype
          AND r.rolname='postgres' AND EXISTS (SELECT 1 FROM pg_catalog.unnest(p.proconfig) cfg(setting)
              WHERE pg_catalog.split_part(setting,'=',1)='search_path' AND pg_catalog.btrim(pg_catalog.split_part(setting,'=',2),'"')='')
    ), 'SECURITY DEFINER, owner postgres, jsonb, search_path vacio'
    UNION ALL
    SELECT 'rpc_execute_privileges', (
        SELECT pg_catalog.count(*) = 3 FROM expected x
        WHERE NOT pg_catalog.has_function_privilege('anon', pg_catalog.to_regprocedure(x.signature), 'EXECUTE')
          AND pg_catalog.has_function_privilege('authenticated', pg_catalog.to_regprocedure(x.signature), 'EXECUTE')
    ), 'anon sin EXECUTE; authenticated con EXECUTE'
    UNION ALL
    SELECT 'qr_table_and_varchar_4', EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a WHERE a.attrelid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
      AND a.attname='iqr_codigo' AND a.atttypid='pg_catalog.varchar'::regtype AND a.atttypmod=8), 'QR-1B iqr_codigo varchar(4)'
    UNION ALL
    SELECT 'qr_rls', EXISTS (SELECT 1 FROM pg_catalog.pg_class WHERE oid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND relrowsecurity AND NOT relforcerowsecurity), 'RLS habilitado'
    UNION ALL
    SELECT 'qr_unique', EXISTS (SELECT 1 FROM pg_catalog.pg_constraint WHERE conrelid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND conname='uq_evp_iqr_cuenta_evento_codigo' AND contype='u')
      AND EXISTS (SELECT 1 FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND c.relname='ux_evp_iqr_invitacion_activa' AND i.indisunique AND i.indpred IS NOT NULL), 'UNIQUE historico y activo'
    UNION ALL
    SELECT 'qr_no_client_direct_privileges', NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) acl LEFT JOIN pg_catalog.pg_roles r ON r.oid=acl.grantee
      WHERE c.oid=pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') AND (acl.grantee=0 OR r.rolname IN ('anon','authenticated')) AND acl.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')), 'sin acceso directo cliente'
    UNION ALL
    SELECT object_name, pg_catalog.to_regclass(object_name) IS NOT NULL, 'dependencia'
    FROM (VALUES ('public.evp_usr_usuario'),('public.evp_ucu_usuario_cuenta'),('public.evp_cta_cuenta'),('public.evp_eve_evento'),('public.evp_inv_invitacion')) required(object_name)
), report AS (
    SELECT check_name, passed, detail, 1 AS display_order FROM checks
    UNION ALL SELECT 'SUMMARY', pg_catalog.bool_and(passed), CASE WHEN pg_catalog.bool_and(passed) THEN 'READY' ELSE 'NOT READY' END, 2 FROM checks
)
SELECT check_name, CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS status, detail FROM report ORDER BY display_order, check_name;
