-- QR-1C-B1: prueba funcional transaccional. Complete CONFIG desde discovery.
-- Todos los cambios, incluidas las RPC, quedan revertidos por ROLLBACK.
BEGIN;
CREATE TEMPORARY TABLE qr_admin_test_results (
    orden integer PRIMARY KEY, prueba text NOT NULL, resultado text NOT NULL, detalle text NOT NULL
) ON COMMIT DROP;

DO $functional$
DECLARE
    master_auth uuid := '397bc597-6e61-4447-a222-dcdb55051f7b';
    admin_auth uuid := 'a3b47ae0-2824-4763-941c-4b38d9785994';
    operator_auth uuid := 'd29465aa-678c-4f00-87fb-cdaed8ea55d9';
    consulta_auth uuid := 'f85e972f-8c72-4556-a302-10b419ee5a7e';
    test_account integer := 2; test_event integer := 1;
    invitation_a integer := 1; invitation_b integer := 2; invitation_c integer := 3;
    other_account integer := 3; other_event integer := 1;
    foreign_event integer := 8; foreign_invitation integer := 72;
    response jsonb; old_qr_uuid uuid; active_code text;
BEGIN
    ASSERT master_auth IS NOT NULL AND admin_auth IS NOT NULL AND operator_auth IS NOT NULL
       AND consulta_auth IS NOT NULL, 'CONFIG: faltan UUID Auth';
    ASSERT test_account IS NOT NULL AND test_event IS NOT NULL AND invitation_a IS NOT NULL
       AND invitation_b IS NOT NULL AND invitation_c IS NOT NULL AND other_account IS NOT NULL
       AND other_event IS NOT NULL AND foreign_event IS NOT NULL AND foreign_invitation IS NOT NULL, 'CONFIG: faltan IDs';
    ASSERT invitation_a <> invitation_b AND invitation_a <> invitation_c AND invitation_b <> invitation_c,
       'CONFIG: invitaciones TARGET repetidas';
    ASSERT EXISTS (SELECT 1 FROM public.evp_usr_usuario WHERE usr_usuario_auth_uuid = master_auth
                  AND usr_estado = 'Activo' AND usr_es_usuario_master), 'CONFIG MASTER invalida';
    ASSERT EXISTS (SELECT 1 FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
                  WHERE u.usr_usuario_auth_uuid = admin_auth AND u.usr_estado = 'Activo' AND NOT u.usr_es_usuario_master
                    AND r.ucu_cuenta_id = test_account AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Administrador'), 'CONFIG ADMIN invalida';
    ASSERT EXISTS (SELECT 1 FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
                  WHERE u.usr_usuario_auth_uuid = operator_auth AND u.usr_estado = 'Activo' AND r.ucu_cuenta_id = test_account
                    AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Operador'), 'CONFIG OPERADOR invalida';
    ASSERT EXISTS (SELECT 1 FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
                  WHERE u.usr_usuario_auth_uuid = consulta_auth AND u.usr_estado = 'Activo' AND r.ucu_cuenta_id = test_account
                    AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Consulta'), 'CONFIG CONSULTA invalida';
    ASSERT EXISTS (SELECT 1 FROM public.evp_usr_usuario u WHERE u.usr_usuario_auth_uuid = operator_auth AND u.usr_estado = 'Activo'
                  AND NOT u.usr_es_usuario_master AND NOT EXISTS (SELECT 1 FROM public.evp_ucu_usuario_cuenta r WHERE r.ucu_usuario_id = u.usr_usuario_id
                  AND r.ucu_cuenta_id = other_account AND r.ucu_estado = 'Activo')), 'CONFIG OPERADOR sin acceso a cuenta ajena invalida';
    ASSERT EXISTS (SELECT 1 FROM public.evp_cta_cuenta c JOIN public.evp_eve_evento e ON e.eve_cuenta_id = c.cta_cuenta_id
                  WHERE c.cta_cuenta_id = test_account AND c.cta_estado = 'Activo' AND e.eve_evento_id = test_event
                    AND e.eve_estado = 'Activo' AND e.eve_fase_evento IN ('Pre_evento', 'En_proceso')
                    AND e.eve_fecha_hora_inicio IS NOT NULL AND e.eve_fecha_hora_fin > e.eve_fecha_hora_inicio), 'CONFIG EVENT invalido';
    ASSERT (SELECT count(*) = 3 FROM public.evp_inv_invitacion i WHERE i.inv_cuenta_id = test_account AND i.inv_evento_id = test_event
                  AND i.inv_estado = 'Activo' AND i.inv_invitacion_id IN (invitation_a, invitation_b, invitation_c)), 'CONFIG TARGET invalida';
    ASSERT NOT EXISTS (SELECT 1 FROM public.evp_inv_invitacion i WHERE i.inv_cuenta_id = test_account AND i.inv_evento_id = test_event
                  AND i.inv_invitacion_id = foreign_invitation), 'CONFIG FOREIGN pertenece al TARGET';
    ASSERT EXISTS (SELECT 1 FROM public.evp_inv_invitacion i WHERE i.inv_cuenta_id = test_account AND i.inv_evento_id = foreign_event
                  AND i.inv_invitacion_id = foreign_invitation AND i.inv_estado = 'Activo'), 'CONFIG FOREIGN invalida';
    ASSERT NOT EXISTS (SELECT 1 FROM public.evp_iqr_invitacion_qr q WHERE q.iqr_codigo IN ('AB12','E5F6','K7M9','L8N0','X7K2')
                  OR (q.iqr_cuenta_id = test_account AND q.iqr_evento_id = test_event AND q.iqr_invitacion_id IN (invitation_a, invitation_b, invitation_c))),
                  'CONFIG QR previo o codigo de prueba usado';

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', master_auth::text, true);
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_a, '  ab12  ');
    ASSERT response->>'codigo_resultado' = 'QR_CREATED' AND response->>'codigo' = 'AB12',
        'MASTER_CREATE esperaba QR_CREATED/AB12, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    ASSERT EXISTS (SELECT 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
                  AND iqr_invitacion_id = invitation_a AND iqr_codigo = 'AB12');
    INSERT INTO qr_admin_test_results VALUES (10, 'MASTER_CREATE_CORRECT_INVITATION', 'PASS', 'Master asocia AB12 normalizado');
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_c, 'A1-2');
    ASSERT response->>'codigo_resultado' = 'QR_INVALID_FORMAT',
        'INVALID_FORMAT esperaba QR_INVALID_FORMAT, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    ASSERT NOT EXISTS (SELECT 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
                  AND iqr_invitacion_id = invitation_c AND iqr_estado = 'Activo'), 'INVALID_FORMAT creo QR inesperado para invitation_c';
    INSERT INTO qr_admin_test_results VALUES (15, 'INVALID_FORMAT', 'PASS', 'Formato invalido rechazado sin crear QR');
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_c, 'AB12');
    ASSERT response->>'codigo_resultado' = 'QR_CODE_CONFLICT',
        'DUPLICATE_CODE esperaba QR_CODE_CONFLICT, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    ASSERT NOT EXISTS (SELECT 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
                  AND iqr_invitacion_id = invitation_c AND iqr_estado = 'Activo'), 'DUPLICATE_CODE creo QR inesperado para invitation_c';
    INSERT INTO qr_admin_test_results VALUES (20, 'DUPLICATE_CODE_DENIED', 'PASS', 'AB12 ya pertenece a invitation_a');
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_c, '  x7k2  ');
    ASSERT response->>'codigo_resultado' = 'QR_CREATED' AND response->>'codigo' = 'X7K2',
        'TRIM_UPPER esperaba QR_CREATED/X7K2, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (25, 'TRIM_UPPER_NORMALIZATION', 'PASS', 'Espacios y minusculas producen X7K2');
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_FOUND' AND response->>'codigo' = 'AB12',
        'MASTER_GET esperaba QR_FOUND/AB12, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (30, 'MASTER_GET', 'PASS', 'Consulta QR activo');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', admin_auth::text, true);
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, invitation_b, 'K7M9');
    ASSERT response->>'codigo_resultado' = 'QR_CREATED',
        'ADMIN_CREATE esperaba QR_CREATED, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (40, 'ADMIN_CREATE', 'PASS', 'Administrador crea en su ambito');
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_b);
    ASSERT response->>'codigo_resultado' = 'QR_FOUND',
        'ADMIN_GET esperaba QR_FOUND, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (50, 'ADMIN_GET', 'PASS', 'Administrador consulta en su ambito');
    response := public.evp_admin_regenerar_qr_invitacion(test_account, test_event, invitation_b, 'L8N0');
    ASSERT response->>'codigo_resultado' = 'QR_REGENERATED' AND response->>'codigo' = 'L8N0',
        'ADMIN_REGENERATE esperaba QR_REGENERATED/L8N0, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (60, 'ADMIN_REGENERATE', 'PASS', 'Administrador regenera en su ambito');
    response := public.evp_admin_crear_qr_invitacion(other_account, other_event, 2147483647, 'P2Q3');
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED',
        'ADMIN_OTHER_ACCOUNT esperaba QR_NOT_ALLOWED, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (70, 'ADMIN_OTHER_ACCOUNT_EVENT_DENIED', 'PASS', 'Cuenta/evento fuera de alcance rechazados');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', operator_auth::text, true);
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED',
        'OPERATOR_DENIED esperaba QR_NOT_ALLOWED, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (80, 'OPERATOR_DENIED', 'PASS', 'Operador rechazado');
    PERFORM pg_catalog.set_config('request.jwt.claim.sub', consulta_auth::text, true);
    response := public.evp_admin_obtener_qr_invitacion(test_account, test_event, invitation_a);
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED',
        'CONSULTA_DENIED esperaba QR_NOT_ALLOWED, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (90, 'CONSULTA_DENIED', 'PASS', 'Consulta rechazada');
    PERFORM pg_catalog.set_config('request.jwt.claim.sub', operator_auth::text, true);
    response := public.evp_admin_obtener_qr_invitacion(other_account, other_event, 2147483647);
    ASSERT response->>'codigo_resultado' = 'QR_NOT_ALLOWED',
        'NO_ACCESS_TO_OPERATION_ACCOUNT esperaba QR_NOT_ALLOWED, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (100, 'NO_ACCESS_TO_OPERATION_ACCOUNT_DENIED', 'PASS', 'Operador cuenta 2 sin acceso a cuenta 3 rechazado');

    PERFORM pg_catalog.set_config('request.jwt.claim.sub', master_auth::text, true);
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, foreign_invitation, 'P2Q3');
    ASSERT response->>'codigo_resultado' = 'QR_INVITATION_NOT_FOUND',
        'FOREIGN_INVITATION esperaba QR_INVITATION_NOT_FOUND, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (120, 'FOREIGN_INVITATION_DENIED', 'PASS', 'Invitacion externa rechazada');
    response := public.evp_admin_crear_qr_invitacion(test_account, test_event, 2147483647, 'P2Q3');
    ASSERT response->>'codigo_resultado' = 'QR_INVITATION_NOT_FOUND' AND response - 'ok' - 'codigo_resultado' = '{}'::jsonb,
        'MISSING_INVITATION esperaba error controlado, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    INSERT INTO qr_admin_test_results VALUES (130, 'MISSING_INVITATION_CONTROLLED', 'PASS', 'Sin datos internos en error');

    SELECT iqr_invitacion_qr_uuid INTO old_qr_uuid FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account
      AND iqr_evento_id = test_event AND iqr_invitacion_id = invitation_a AND iqr_estado = 'Activo';
    response := public.evp_admin_regenerar_qr_invitacion(test_account, test_event, invitation_a, 'E5F6');
    ASSERT response->>'codigo_resultado' = 'QR_REGENERATED' AND response->>'codigo' = 'E5F6',
        'MASTER_REGENERATE esperaba QR_REGENERATED/E5F6, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    ASSERT EXISTS (SELECT 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_invitacion_qr_uuid = old_qr_uuid AND iqr_estado = 'Revocado'
                  AND iqr_fecha_revocacion IS NOT NULL);
    INSERT INTO qr_admin_test_results VALUES (140, 'MASTER_REGENERATE_REVOKES', 'PASS', 'Anterior Revocado, nuevo activo');
    ASSERT (SELECT count(*) = 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
            AND iqr_invitacion_id = invitation_a AND iqr_estado = 'Activo');
    INSERT INTO qr_admin_test_results VALUES (150, 'ONE_ACTIVE_QR', 'PASS', 'Una activa por invitacion');
    response := public.evp_admin_regenerar_qr_invitacion(test_account, test_event, invitation_a, 'L8N0');
    ASSERT response->>'codigo_resultado' = 'QR_CODE_CONFLICT',
        'REGENERATE_CONFLICT esperaba QR_CODE_CONFLICT, obtuvo: ' || coalesce(response->>'codigo_resultado', 'NULL');
    SELECT iqr_codigo INTO active_code FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = test_account AND iqr_evento_id = test_event
      AND iqr_invitacion_id = invitation_a AND iqr_estado = 'Activo';
    ASSERT active_code = 'E5F6', 'REGENERATE_CONFLICT esperaba conservar E5F6, obtuvo: ' || coalesce(active_code, 'NULL');
    INSERT INTO qr_admin_test_results VALUES (160, 'REGENERATE_CONFLICT_PRESERVES', 'PASS', 'Fallo conserva QR activo');
    ASSERT (SELECT count(*) = 17 FROM qr_admin_test_results WHERE resultado = 'PASS');
    INSERT INTO qr_admin_test_results VALUES (170, 'SUMMARY', 'PASS', '17/17 casos superados; ROLLBACK restaura datos');
END
$functional$;
SELECT prueba, resultado, detalle FROM qr_admin_test_results ORDER BY orden;
ROLLBACK;

-- Administrador tiene acceso a todos los eventos de su cuenta por diseno; por eso
-- "evento sin acceso" se prueba con otra cuenta. QR-2 debe rechazar Revocados.
