-- Verificacion estructural READ-ONLY posterior a QR-1C-B1.
DO $verification$
DECLARE
    v_signature text;
    v_function_oid oid;
    v_table_oid oid := pg_catalog.to_regclass('public.evp_iqr_invitacion_qr');
BEGIN
    FOREACH v_signature IN ARRAY ARRAY[
        'public.evp_admin_obtener_qr_invitacion(integer,integer,integer)',
        'public.evp_admin_crear_qr_invitacion(integer,integer,integer,text)',
        'public.evp_admin_regenerar_qr_invitacion(integer,integer,integer,text)'
    ] LOOP
        v_function_oid := pg_catalog.to_regprocedure(v_signature);
        IF v_function_oid IS NULL THEN RAISE EXCEPTION 'Falta %', v_signature; END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_proc AS p
            JOIN pg_catalog.pg_roles AS r ON r.oid = p.proowner
            WHERE p.oid = v_function_oid
              AND p.prokind = 'f'
              AND p.prorettype = 'pg_catalog.jsonb'::pg_catalog.regtype
              AND pg_catalog.pg_get_function_result(p.oid) = 'jsonb'
              AND p.prosecdef
              AND r.rolname = 'postgres'
              AND EXISTS (
                  SELECT 1 FROM pg_catalog.unnest(p.proconfig) AS cfg(setting)
                  WHERE pg_catalog.split_part(setting, '=', 1) = 'search_path'
                    AND pg_catalog.btrim(
                        pg_catalog.split_part(setting, '=', 2), '"'
                    ) = ''
              )
        ) THEN RAISE EXCEPTION 'Metadatos inseguros o retorno incorrecto: %', v_signature; END IF;
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_proc AS p
            CROSS JOIN LATERAL pg_catalog.aclexplode(
                coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
            ) AS acl
            WHERE p.oid = v_function_oid
              AND acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'
        ) THEN RAISE EXCEPTION 'PUBLIC conserva EXECUTE: %', v_signature; END IF;
        IF pg_catalog.has_function_privilege('anon', v_function_oid, 'EXECUTE') THEN
            RAISE EXCEPTION 'anon conserva EXECUTE: %', v_signature;
        END IF;
        IF NOT pg_catalog.has_function_privilege('authenticated', v_function_oid, 'EXECUTE') THEN
            RAISE EXCEPTION 'authenticated no tiene EXECUTE: %', v_signature;
        END IF;
    END LOOP;

    IF v_table_oid IS NULL THEN RAISE EXCEPTION 'Falta tabla QR-1B'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class
        WHERE oid = v_table_oid AND relrowsecurity AND NOT relforcerowsecurity
    ) THEN RAISE EXCEPTION 'RLS QR-1B alterado'; END IF;
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute
        WHERE attrelid = v_table_oid AND attnum > 0 AND NOT attisdropped) <> 10 THEN
        RAISE EXCEPTION 'Columnas QR-1B alteradas';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = v_table_oid AND conname = 'uq_evp_iqr_cuenta_evento_codigo' AND contype = 'u'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_index AS i JOIN pg_catalog.pg_class AS c ON c.oid = i.indexrelid
        WHERE i.indrelid = v_table_oid AND c.relname = 'ux_evp_iqr_invitacion_activa'
          AND i.indisunique AND i.indpred IS NOT NULL
    ) THEN RAISE EXCEPTION 'Garantias UNIQUE QR-1B alteradas'; END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid = v_table_oid) THEN
        RAISE EXCEPTION 'QR-1B adquirio politicas directas';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS c
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
        ) AS acl
        WHERE c.oid = v_table_oid AND acl.grantee = 0
          AND acl.privilege_type IN (
              'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
          )
    ) THEN RAISE EXCEPTION 'PUBLIC conserva privilegios directos sobre QR-1B'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class AS c
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
        ) AS acl
        JOIN pg_catalog.pg_roles AS r ON r.oid = acl.grantee
        WHERE c.oid = v_table_oid
          AND r.rolname IN ('anon', 'authenticated')
          AND acl.privilege_type IN (
              'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
          )
    ) THEN
        RAISE EXCEPTION 'Cliente conserva privilegios directos sobre QR-1B';
    END IF;
END
$verification$;

SELECT 'PASS' AS invitation_qr_admin_rpc_structure;
