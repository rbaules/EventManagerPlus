-- QR-1B preflight READ-ONLY.
-- Ejecutar inmediatamente antes de la migracion. No corrige ningun hallazgo.
WITH expected_object_names(object_name) AS (
    VALUES
        ('pk_evp_iqr_invitacion_qr'),
        ('fk_evp_iqr_invitacion_qr_invitacion'),
        ('uq_evp_iqr_cuenta_evento_codigo'),
        ('ck_evp_iqr_codigo_formato'),
        ('ck_evp_iqr_estado'),
        ('ck_evp_iqr_rango_vigencia'),
        ('ck_evp_iqr_revocacion_coherente'),
        ('ux_evp_iqr_invitacion_activa')
),
name_conflicts AS (
    SELECT DISTINCT n.object_name
    FROM expected_object_names AS n
    WHERE EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS c
        JOIN pg_catalog.pg_namespace AS ns ON ns.oid = c.connamespace
        WHERE ns.nspname = 'public' AND c.conname::text = n.object_name
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        JOIN pg_catalog.pg_namespace AS ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'public'
          AND c.relkind IN ('i', 'I')
          AND c.relname::text = n.object_name
    )
),
checks(check_name, passed, detail) AS (
    SELECT
        'target_table_absent',
        pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') IS NULL,
        coalesce(
            pg_catalog.to_regclass('public.evp_iqr_invitacion_qr')::text,
            'public.evp_iqr_invitacion_qr no existe'
        )
    UNION ALL
    SELECT
        'invitation_table_exists',
        pg_catalog.to_regclass('public.evp_inv_invitacion') IS NOT NULL,
        coalesce(
            pg_catalog.to_regclass('public.evp_inv_invitacion')::text,
            'FALTA public.evp_inv_invitacion'
        )
    UNION ALL
    SELECT
        'invitation_composite_pk',
        EXISTS (
            SELECT 1
            FROM pg_catalog.pg_constraint AS c
            WHERE c.conrelid = pg_catalog.to_regclass('public.evp_inv_invitacion')
              AND c.contype = 'p'
              AND ARRAY(
                  SELECT a.attname::text
                  FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
                  JOIN pg_catalog.pg_attribute AS a
                    ON a.attrelid = c.conrelid AND a.attnum = k.attnum
                  ORDER BY k.ord
              ) = ARRAY[
                  'inv_cuenta_id',
                  'inv_evento_id',
                  'inv_invitacion_id'
              ]::text[]
        ),
        'PK esperada: (inv_cuenta_id, inv_evento_id, inv_invitacion_id)'
    UNION ALL
    SELECT
        'uuid_generator_available',
        pg_catalog.to_regprocedure('extensions.gen_random_uuid()') IS NOT NULL,
        coalesce(
            pg_catalog.to_regprocedure('extensions.gen_random_uuid()')::text,
            'FALTA extensions.gen_random_uuid()'
        )
    UNION ALL
    SELECT
        'role_anon_exists',
        EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'anon'),
        'rol anon'
    UNION ALL
    SELECT
        'role_authenticated_exists',
        EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'authenticated'),
        'rol authenticated'
    UNION ALL
    SELECT
        'object_names_available',
        NOT EXISTS (SELECT 1 FROM name_conflicts),
        coalesce(
            (SELECT 'CONFLICTOS: ' || string_agg(object_name, ', ' ORDER BY object_name)
             FROM name_conflicts),
            'sin conflictos de nombres'
        )
),
report AS (
    SELECT check_name, passed, detail, 1 AS display_order
    FROM checks
    UNION ALL
    SELECT
        'SUMMARY',
        pg_catalog.bool_and(passed),
        CASE WHEN pg_catalog.bool_and(passed) THEN 'READY' ELSE 'NOT READY' END,
        2
    FROM checks
)
SELECT
    check_name,
    CASE WHEN passed THEN 'PASS' ELSE 'FAIL' END AS status,
    detail
FROM report
ORDER BY display_order, check_name;
