-- Verificacion READ-ONLY para ejecutar despues de aplicar QR-1B en un entorno controlado.
-- No crea, modifica ni elimina datos u objetos.
DO $verification$
DECLARE
    v_table_oid oid := to_regclass('public.evp_iqr_invitacion_qr');
    v_columns text[];
    v_expected_columns constant text[] := ARRAY[
        'iqr_invitacion_qr_uuid:uuid:NO:extensions.gen_random_uuid()',
        'iqr_cuenta_id:integer:NO:',
        'iqr_evento_id:integer:NO:',
        'iqr_invitacion_id:integer:NO:',
        'iqr_codigo:character varying(4):NO:',
        'iqr_estado:character varying(15):NO:''Activo''::character varying',
        'iqr_valido_desde:timestamp with time zone:NO:',
        'iqr_valido_hasta:timestamp with time zone:NO:',
        'iqr_fecha_creacion:timestamp with time zone:NO:now()',
        'iqr_fecha_revocacion:timestamp with time zone:YES:'
    ];
    v_definition text;
    v_index_predicate text;
    v_original_token record;
BEGIN
    IF v_table_oid IS NULL THEN
        RAISE EXCEPTION 'Falta public.evp_iqr_invitacion_qr';
    END IF;

    SELECT array_agg(
        a.attname || ':' || pg_catalog.format_type(a.atttypid, a.atttypmod) || ':' ||
        CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END || ':' ||
        coalesce(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '')
        ORDER BY a.attnum
    )
    INTO v_columns
    FROM pg_catalog.pg_attribute AS a
    LEFT JOIN pg_catalog.pg_attrdef AS d
      ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE a.attrelid = v_table_oid
      AND a.attnum > 0
      AND NOT a.attisdropped;

    IF v_columns IS DISTINCT FROM v_expected_columns THEN
        RAISE EXCEPTION 'Columnas, tipos, nulabilidad o defaults inesperados: %', v_columns;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = v_table_oid AND conname = 'pk_evp_iqr_invitacion_qr'
          AND contype = 'p'
          AND ARRAY(
              SELECT a.attname::text
              FROM unnest(conkey) WITH ORDINALITY AS k(attnum, ord)
              JOIN pg_catalog.pg_attribute AS a
                ON a.attrelid = conrelid AND a.attnum = k.attnum
              ORDER BY k.ord
          ) = ARRAY['iqr_invitacion_qr_uuid']::text[]
    ) THEN RAISE EXCEPTION 'PK QR ausente o incorrecta'; END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = v_table_oid AND conname = 'fk_evp_iqr_invitacion_qr_invitacion'
          AND contype = 'f'
          AND confrelid = 'public.evp_inv_invitacion'::regclass
          AND confupdtype = 'a' AND confdeltype = 'a'
          AND ARRAY(
              SELECT a.attname::text
              FROM unnest(conkey) WITH ORDINALITY AS k(attnum, ord)
              JOIN pg_catalog.pg_attribute AS a
                ON a.attrelid = conrelid AND a.attnum = k.attnum
              ORDER BY k.ord
          ) = ARRAY[
              'iqr_cuenta_id', 'iqr_evento_id', 'iqr_invitacion_id'
          ]::text[]
          AND ARRAY(
              SELECT a.attname::text
              FROM unnest(confkey) WITH ORDINALITY AS k(attnum, ord)
              JOIN pg_catalog.pg_attribute AS a
                ON a.attrelid = confrelid AND a.attnum = k.attnum
              ORDER BY k.ord
          ) = ARRAY[
              'inv_cuenta_id', 'inv_evento_id', 'inv_invitacion_id'
          ]::text[]
    ) THEN RAISE EXCEPTION 'FK compuesta QR ausente o incorrecta'; END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_constraint
        WHERE conrelid = v_table_oid AND conname = 'uq_evp_iqr_cuenta_evento_codigo'
          AND contype = 'u'
          AND ARRAY(
              SELECT a.attname::text
              FROM unnest(conkey) WITH ORDINALITY AS k(attnum, ord)
              JOIN pg_catalog.pg_attribute AS a
                ON a.attrelid = conrelid AND a.attnum = k.attnum
              ORDER BY k.ord
          ) = ARRAY['iqr_cuenta_id', 'iqr_evento_id', 'iqr_codigo']::text[]
    ) THEN RAISE EXCEPTION 'UNIQUE de codigo QR ausente o incorrecta'; END IF;

    SELECT pg_catalog.pg_get_constraintdef(oid) INTO v_definition
    FROM pg_catalog.pg_constraint
    WHERE conrelid = v_table_oid AND conname = 'ck_evp_iqr_codigo_formato' AND contype = 'c';
    IF v_definition IS NULL OR position('^[A-Z0-9]{4}$' IN v_definition) = 0 THEN
        RAISE EXCEPTION 'CHECK de formato de codigo ausente o incorrecto: %', v_definition;
    END IF;

    SELECT pg_catalog.pg_get_constraintdef(oid) INTO v_definition
    FROM pg_catalog.pg_constraint
    WHERE conrelid = v_table_oid AND conname = 'ck_evp_iqr_estado' AND contype = 'c';
    IF v_definition IS NULL OR position('Activo' IN v_definition) = 0
       OR position('Revocado' IN v_definition) = 0 THEN
        RAISE EXCEPTION 'CHECK de estado ausente o incorrecto: %', v_definition;
    END IF;

    SELECT pg_catalog.pg_get_constraintdef(oid) INTO v_definition
    FROM pg_catalog.pg_constraint
    WHERE conrelid = v_table_oid AND conname = 'ck_evp_iqr_rango_vigencia' AND contype = 'c';
    IF v_definition IS NULL OR position('iqr_valido_hasta > iqr_valido_desde' IN v_definition) = 0 THEN
        RAISE EXCEPTION 'CHECK de vigencia ausente o incorrecto: %', v_definition;
    END IF;

    SELECT pg_catalog.pg_get_constraintdef(oid) INTO v_definition
    FROM pg_catalog.pg_constraint
    WHERE conrelid = v_table_oid AND conname = 'ck_evp_iqr_revocacion_coherente' AND contype = 'c';
    IF v_definition IS NULL OR position('Activo' IN v_definition) = 0
       OR position('Revocado' IN v_definition) = 0
       OR position('iqr_fecha_revocacion IS NULL' IN v_definition) = 0
       OR position('iqr_fecha_revocacion IS NOT NULL' IN v_definition) = 0 THEN
        RAISE EXCEPTION 'CHECK de revocacion ausente o incorrecto: %', v_definition;
    END IF;

    SELECT pg_catalog.pg_get_expr(i.indpred, i.indrelid)
    INTO v_index_predicate
    FROM pg_catalog.pg_index AS i
    JOIN pg_catalog.pg_class AS c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_table_oid
      AND c.relname = 'ux_evp_iqr_invitacion_activa'
      AND i.indisunique
      AND i.indnkeyatts = 3
      AND ARRAY(
          SELECT a.attname::text
          FROM unnest(i.indkey::smallint[]) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_catalog.pg_attribute AS a
            ON a.attrelid = i.indrelid AND a.attnum = k.attnum
          WHERE k.ord <= i.indnkeyatts
          ORDER BY k.ord
      ) = ARRAY['iqr_cuenta_id', 'iqr_evento_id', 'iqr_invitacion_id']::text[]
      AND i.indpred IS NOT NULL;
    IF v_index_predicate IS NULL
       OR regexp_replace(v_index_predicate, '[()[:space:]]', '', 'g')
          <> 'iqr_estado::text=''Activo''::text' THEN
        RAISE EXCEPTION 'Indice UNIQUE parcial de QR activa ausente o incorrecto: %',
            v_index_predicate;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_class
        WHERE oid = v_table_oid AND relrowsecurity AND NOT relforcerowsecurity
    ) THEN RAISE EXCEPTION 'RLS debe estar habilitado sin FORCE RLS'; END IF;

    IF EXISTS (SELECT 1 FROM pg_catalog.pg_policy WHERE polrelid = v_table_oid) THEN
        RAISE EXCEPTION 'La tabla QR no debe tener politicas directas';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS role ON role.oid = acl.grantee
        WHERE c.oid = v_table_oid
          AND (acl.grantee = 0 OR role.rolname IN ('anon', 'authenticated'))
          AND acl.privilege_type IN (
              'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
          )
    ) THEN
        RAISE EXCEPTION 'PUBLIC, anon o authenticated conserva privilegios sobre la tabla QR';
    END IF;

    SELECT data_type, character_maximum_length, is_nullable, column_default
    INTO v_original_token
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'evp_inv_invitacion'
      AND column_name = 'inv_token_qr_invitacion';
    IF NOT FOUND
       OR v_original_token.data_type <> 'character varying'
       OR v_original_token.character_maximum_length <> 100
       OR v_original_token.is_nullable <> 'YES'
       OR v_original_token.column_default IS NOT NULL THEN
        RAISE EXCEPTION 'inv_token_qr_invitacion fue alterada';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS c
        JOIN pg_catalog.pg_attribute AS a
          ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.conrelid = 'public.evp_inv_invitacion'::regclass
          AND c.contype = 'u' AND cardinality(c.conkey) = 1
          AND a.attname = 'inv_token_qr_invitacion'
    ) THEN RAISE EXCEPTION 'UNIQUE global de inv_token_qr_invitacion ausente'; END IF;
END
$verification$;

SELECT 'PASS' AS invitation_qr_storage_verification;
