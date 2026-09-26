-- QR-1C-B1: prueba funcional transaccional. NO ejecutar hasta completar CONFIG.
-- Requiere UUID Auth reales para Master, Administrador, Operador y Consulta;
-- una cuenta/evento Activos en Pre_evento o En_proceso con horario valido; y
-- tres invitaciones Activas controladas, sin historial QR, del mismo evento.
BEGIN;

-- ACTIVACION: completar CONFIG y descomentar solo la linea siguiente.
-- DO $$ BEGIN PERFORM pg_catalog.set_config('eventplus.run_qr_admin_functional','on',true); END $$;

CREATE TEMPORARY TABLE qr_admin_test_results (
    orden integer PRIMARY KEY,
    prueba text NOT NULL,
    resultado text NOT NULL,
    detalle text NOT NULL
) ON COMMIT DROP;

DO $functional$
DECLARE
    -- CONFIG: sustituir NULL exclusivamente con fixtures previamente auditadas.
    master_auth uuid := NULL;
    admin_auth uuid := NULL;
    operator_auth uuid := NULL;
    consulta_auth uuid := NULL;
    test_account integer := NULL;
    test_event integer := NULL;
    invitation_a integer := NULL;
    invitation_b integer := NULL;
    invitation_c integer := NULL;
    response jsonb;
    old_qr_uuid uuid;
BEGIN
    IF coalesce(pg_catalog.current_setting('eventplus.run_qr_admin_functional', true), 'off') <> 'on' THEN
        RAISE NOTICE 'Funcional QR omitida: complete CONFIG y active eventplus.run_qr_admin_functional';
        RETURN;
    END IF;

    ASSERT master_auth IS NOT NULL AND admin_auth IS NOT NULL
       AND operator_auth IS NOT NULL AND consulta_auth IS NOT NULL,
       'CONFIG: faltan UUID Auth';
    ASSERT test_account IS NOT NULL AND test_event IS NOT NULL
       AND invitation_a IS NOT NULL AND invitation_b IS NOT NULL AND invitation_c IS NOT NULL,
       'CONFIG: faltan IDs controlados';
    ASSERT invitation_a <> invitation_b AND invitation_a <> invitation_c AND invitation_b <> invitation_c,
       'CONFIG: las tres invitaciones deben ser distintas';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_usr_usuario
        WHERE usr_usuario_auth_uuid = master_auth AND usr_estado = 'Activo' AND usr_es_usuario_master
    ), 'CONFIG MASTER invalida';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_usr_usuario AS u
        JOIN public.evp_ucu_usuario_cuenta AS r ON r.ucu_usuario_id = u.usr_usuario_id
        WHERE u.usr_usuario_auth_uuid = admin_auth AND u.usr_estado = 'Activo'
          AND NOT u.usr_es_usuario_master AND r.ucu_cuenta_id = test_account
          AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Administrador'
    ), 'CONFIG ADMIN invalida';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_usr_usuario AS u
        JOIN public.evp_ucu_usuario_cuenta AS r ON r.ucu_usuario_id = u.usr_usuario_id
        WHERE u.usr_usuario_auth_uuid = operator_auth AND u.usr_estado = 'Activo'
          AND NOT u.usr_es_usuario_master AND r.ucu_cuenta_id = test_account
          AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Operador'
    ), 'CONFIG OPERADOR invalida';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_usr_usuario AS u
        JOIN public.evp_ucu_usuario_cuenta AS r ON r.ucu_usuario_id = u.usr_usuario_id
        WHERE u.usr_usuario_auth_uuid = consulta_auth AND u.usr_estado = 'Activo'
          AND NOT u.usr_es_usuario_master AND r.ucu_cuenta_id = test_account
          AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Consulta'
    ), 'CONFIG CONSULTA invalida';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_cta_cuenta AS c
        JOIN public.evp_eve_evento AS e ON e.eve_cuenta_id = c.cta_cuenta_id
        WHERE c.cta_cuenta_id = test_account AND c.cta_estado = 'Activo'
          AND e.eve_evento_id = test_event AND e.eve_estado = 'Activo'
          AND e.eve_fase_evento IN ('Pre_evento', 'En_proceso')
          AND e.eve_fecha_hora_inicio IS NOT NULL AND e.eve_fecha_hora_fin IS NOT NULL
          AND e.eve_fecha_hora_fin > e.eve_fecha_hora_inicio
    ), 'CONFIG CUENTA/EVENTO invalida';
    ASSERT (
        SELECT pg_catalog.count(*) = 3 FROM public.evp_inv_invitacion
        WHERE inv_cuenta_id = test_account AND inv_evento_id = test_event
          AND inv_invitacion_id IN (invitation_a, invitation_b, invitation_c)
          AND inv_estado = 'Activo'
    ), 'CONFIG INVITACIONES invalida';
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
          AND (iqr_invitacion_id IN (invitation_a, invitation_b, invitation_c)
               OR iqr_codigo IN ('A1B2', 'C3D4', 'E5F6'))
    ), 'CONFIG QR no esta limpia o los codigos de prueba ya fueron usados';

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', master_auth::text, true);
    ASSERT auth.uid() = master_auth;
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_a, 'A1B2');
    ASSERT response->>'codigo_resultado' = 'QR_CREATED';
    INSERT INTO qr_admin_test_results VALUES (10, 'MASTER_CREATE', 'PASS', 'Master creo QR');

    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_a, 'Z9Z9');
    ASSERT response->>'codigo_resultado' = 'QR_ALREADY_EXISTS' AND response->>'codigo' = 'A1B2';
    INSERT INTO qr_admin_test_results VALUES (20, 'CREATE_IDEMPOTENT', 'PASS', 'Segundo create devolvio QR existente');

    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_FOUND' AND response->>'codigo' = 'A1B2';
    INSERT INTO qr_admin_test_results VALUES (30, 'GET_ACTIVE', 'PASS', 'Obtener devolvio QR activa');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', admin_auth::text, true);
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_b, 'C3D4');
    ASSERT response->>'codigo_resultado' = 'QR_CREATED';
    INSERT INTO qr_admin_test_results VALUES (40, 'ADMIN_CREATE', 'PASS', 'Administrador autorizado creo QR');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', operator_auth::text, true);
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED';
    INSERT INTO qr_admin_test_results VALUES (50, 'OPERATOR_DENIED', 'PASS', 'Operador rechazado');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', consulta_auth::text, true);
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED';
    INSERT INTO qr_admin_test_results VALUES (60, 'CONSULTA_DENIED', 'PASS', 'Consulta rechazado');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', master_auth::text, true);
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_c, 'a1b2');
    ASSERT response->>'codigo_resultado' = 'QR_INVALID_FORMAT';
    INSERT INTO qr_admin_test_results VALUES (70, 'INVALID_FORMAT', 'PASS', 'Lowercase rechazado');

    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_c, 'A1B2');
    ASSERT response->>'codigo_resultado' = 'QR_CODE_CONFLICT';
    ASSERT NOT EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
          AND iqr_invitacion_id = invitation_c
    );
    INSERT INTO qr_admin_test_results VALUES (80, 'CREATE_CONFLICT', 'PASS', 'Colision no creo QR');

    SELECT iqr_invitacion_qr_uuid INTO old_qr_uuid
    FROM public.evp_iqr_invitacion_qr
    WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
      AND iqr_invitacion_id = invitation_a AND iqr_estado = 'Activo';
    response := public.evp_admin_regenerar_qr_invitacion(test_account, test_event, invitation_a, 'E5F6');
    ASSERT response->>'codigo_resultado' = 'QR_REGENERATED';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_invitacion_qr_uuid = old_qr_uuid
          AND iqr_estado = 'Revocado' AND iqr_fecha_revocacion IS NOT NULL
    );
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
          AND iqr_invitacion_id = invitation_a AND iqr_codigo = 'E5F6' AND iqr_estado = 'Activo'
    );
    INSERT INTO qr_admin_test_results VALUES (90, 'REGENERATE', 'PASS', 'Anterior revocada y nueva activa');

    response := public.evp_admin_regenerar_qr_invitacion(test_account, test_event, invitation_a, 'C3D4');
    ASSERT response->>'codigo_resultado' = 'QR_CODE_CONFLICT';
    ASSERT EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
          AND iqr_invitacion_id = invitation_a AND iqr_codigo = 'E5F6'
          AND iqr_estado = 'Activo' AND iqr_fecha_revocacion IS NULL
    ), 'La colision de regeneracion no preservo la QR anterior';
    ASSERT (
        SELECT pg_catalog.count(*) = 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
          AND iqr_invitacion_id = invitation_a AND iqr_estado = 'Activo'
    );
    INSERT INTO qr_admin_test_results VALUES (100, 'REGENERATE_CONFLICT_ROLLBACK', 'PASS', 'QR anterior continuo Activa');

    ASSERT (SELECT pg_catalog.count(*) = 10 FROM qr_admin_test_results WHERE resultado = 'PASS');
    INSERT INTO qr_admin_test_results VALUES (110, 'SUMMARY', 'PASS', '10/10 casos funcionales superados');
    RAISE NOTICE 'PASS FUNCTIONAL QR: 10/10; ROLLBACK elimina todos los cambios QR';
END
$functional$;

SELECT prueba, resultado, detalle FROM qr_admin_test_results ORDER BY orden;
ROLLBACK;

-- CONCURRENCIA (dos sesiones, siempre con fixtures controladas y ROLLBACK):
-- A y B configuran el mismo request.jwt.claim.sub autorizado.
-- A: BEGIN; llamar crear/regenerar para una invitacion y mantener transaccion abierta.
-- B: BEGIN; llamar crear/regenerar para la misma invitacion; debe esperar FOR UPDATE.
-- A: ROLLBACK; B continua sin deadlock y se valida su resultado; B: ROLLBACK.
-- Dos regeneraciones quedan serializadas; la futura UI debe impedir doble pulsacion.
