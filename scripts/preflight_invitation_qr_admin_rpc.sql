-- QR-1C-B1 preflight READ-ONLY. No corrige hallazgos.
WITH checks(check_name, passed, detail) AS (
    SELECT 'qr_table_exists', pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') IS NOT NULL,
           'public.evp_iqr_invitacion_qr'
    UNION ALL
    SELECT 'qr_columns', (
        SELECT pg_catalog.count(*) = 10
        FROM pg_catalog.pg_attribute
        WHERE attrelid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND attnum > 0 AND NOT attisdropped
    ), '10 columnas QR-1B'
    UNION ALL
    SELECT 'qr_codigo_varchar_4', EXISTS (
        SELECT 1
        FROM pg_catalog.pg_attribute AS a
        WHERE a.attrelid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND a.attname = 'iqr_codigo' AND a.atttypid = 'pg_catalog.varchar'::pg_catalog.regtype
          AND a.atttypmod = 8
    ), 'iqr_codigo varchar(4)'
    UNION ALL
    SELECT 'qr_historical_unique', EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND conname = 'uq_evp_iqr_cuenta_evento_codigo' AND contype = 'u'
    ), 'UNIQUE historico de codigo'
    UNION ALL
    SELECT 'qr_active_unique', EXISTS (
        SELECT 1 FROM pg_catalog.pg_index AS i
        JOIN pg_catalog.pg_class AS c ON c.oid = i.indexrelid
        WHERE i.indrelid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND c.relname = 'ux_evp_iqr_invitacion_activa'
          AND i.indisunique AND i.indpred IS NOT NULL
    ), 'UNIQUE parcial de QR activa'
    UNION ALL
    SELECT 'qr_required_constraints', (
        SELECT pg_catalog.count(*) = 7
        FROM pg_catalog.pg_constraint
        WHERE conrelid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND conname IN (
              'pk_evp_iqr_invitacion_qr',
              'fk_evp_iqr_invitacion_qr_invitacion',
              'uq_evp_iqr_cuenta_evento_codigo',
              'ck_evp_iqr_codigo_formato',
              'ck_evp_iqr_estado',
              'ck_evp_iqr_rango_vigencia',
              'ck_evp_iqr_revocacion_coherente'
          )
    ), 'PK, FK, UNIQUE y cuatro CHECK de QR-1B'
    UNION ALL
    SELECT object_name, pg_catalog.to_regclass(object_name) IS NOT NULL, object_name
    FROM (VALUES
        ('public.evp_usr_usuario'),
        ('public.evp_ucu_usuario_cuenta'),
        ('public.evp_cta_cuenta'),
        ('public.evp_eve_evento'),
        ('public.evp_inv_invitacion')
    ) AS required_tables(object_name)
    UNION ALL
    SELECT 'auth_uid_exists', pg_catalog.to_regprocedure('auth.uid()') IS NOT NULL, 'auth.uid()'
    UNION ALL
    SELECT 'qr_rls_enabled_no_force', EXISTS (
        SELECT 1 FROM pg_catalog.pg_class
        WHERE oid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND relrowsecurity AND NOT relforcerowsecurity
    ), 'RLS habilitado; owner SECURITY DEFINER puede operar'
    UNION ALL
    SELECT 'qr_no_client_direct_privileges', NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS r ON r.oid = acl.grantee
        WHERE c.oid = pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')
          AND (acl.grantee = 0 OR r.rolname IN ('anon', 'authenticated'))
          AND acl.privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
    ), 'sin privilegios directos para PUBLIC/anon/authenticated'
    UNION ALL
    SELECT signature, pg_catalog.to_regprocedure(signature) IS NULL, 'firma libre'
    FROM (VALUES
        ('public.evp_admin_obtener_qr_invitacion(integer,integer,integer)'),
        ('public.evp_admin_crear_qr_invitacion(integer,integer,integer,text)'),
        ('public.evp_admin_regenerar_qr_invitacion(integer,integer,integer,text)')
    ) AS target_functions(signature)
), report AS (
    SELECT check_name, passed, detail, 1 AS display_order FROM checks
    UNION ALL
    SELECT 'SUMMARY', pg_catalog.bool_and(passed),
           CASE WHEN pg_catalog.bool_and(passed) THEN 'READY' ELSE 'NOT READY' END, 2
    FROM checks
)
SELECT check_name, CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS status, detail
FROM report
ORDER BY display_order, check_name;
