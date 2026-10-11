-- KIOSK-INDEPENDENT-0E1 preflight READ-ONLY. No corrige hallazgos.
WITH checks(check_name, passed, detail) AS (
    SELECT 'pin_table_exists', pg_catalog.to_regclass('public.evp_kpa_kiosco_pin_administrativo') IS NOT NULL,
           'tabla PIN administrativo'
    UNION ALL
    SELECT 'pin_table_rls_and_no_direct_client_access', EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.oid = pg_catalog.to_regclass('public.evp_kpa_kiosco_pin_administrativo')
          AND c.relrowsecurity
    ) AND NOT pg_catalog.has_table_privilege('authenticated', 'public.evp_kpa_kiosco_pin_administrativo', 'SELECT')
      AND NOT pg_catalog.has_table_privilege('anon', 'public.evp_kpa_kiosco_pin_administrativo', 'SELECT'),
      'hash no legible directamente por cliente'
    UNION ALL
    SELECT 'pin_hash_column_exists', EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
        WHERE a.attrelid = pg_catalog.to_regclass('public.evp_kpa_kiosco_pin_administrativo')
          AND a.attname = 'kpa_pin_hash' AND a.attnum > 0 AND NOT a.attisdropped
    ), 'kpa_pin_hash'
    UNION ALL
    SELECT 'pgcrypto_bcrypt_available', pg_catalog.to_regprocedure('extensions.crypt(text,text)') IS NOT NULL
        AND pg_catalog.to_regprocedure('extensions.gen_salt(text,integer)') IS NOT NULL,
        'extensions.crypt + extensions.gen_salt'
    UNION ALL
    SELECT 'validate_rpc_secure_and_granted', EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid = pg_catalog.to_regprocedure('public.evp_kpa_validar_pin_administrativo(integer,integer,text)')
          AND p.prosecdef
          AND pg_catalog.array_to_string(p.proconfig, ',') LIKE '%search_path=%'
    ) AND pg_catalog.has_function_privilege('authenticated', 'public.evp_kpa_validar_pin_administrativo(integer,integer,text)', 'EXECUTE')
      AND NOT pg_catalog.has_function_privilege('anon', 'public.evp_kpa_validar_pin_administrativo(integer,integer,text)', 'EXECUTE'),
      'SECURITY DEFINER, search_path y solo authenticated'
    UNION ALL
    SELECT 'configure_rpc_secure_and_granted', EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
        WHERE p.oid = pg_catalog.to_regprocedure('public.evp_kpa_configurar_pin_administrativo(integer,integer,text)')
          AND p.prosecdef
          AND pg_catalog.array_to_string(p.proconfig, ',') LIKE '%search_path=%'
    ) AND pg_catalog.has_function_privilege('authenticated', 'public.evp_kpa_configurar_pin_administrativo(integer,integer,text)', 'EXECUTE')
      AND NOT pg_catalog.has_function_privilege('anon', 'public.evp_kpa_configurar_pin_administrativo(integer,integer,text)', 'EXECUTE'),
      'rotacion solo por RPC autenticada'
), report AS (
    SELECT check_name, passed, detail, 1 AS display_order FROM checks
    UNION ALL SELECT 'SUMMARY', pg_catalog.bool_and(passed),
        CASE WHEN pg_catalog.bool_and(passed) THEN 'READY' ELSE 'NOT READY' END, 2 FROM checks
)
SELECT check_name, CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS status, detail
FROM report ORDER BY display_order, check_name;
