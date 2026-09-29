-- QR-3A fixture persistente para prueba manual. Ejecutar como administrador confiable
-- en SQL Editor. Si falla, ejecute ROLLBACK; no deja un fixture parcial confirmado.
-- Los IDs se delegan a los triggers oficiales: INSERT con NULL calcula MAX(id) + 1
-- bajo advisory lock y RETURNING conserva los IDs realmente asignados.
BEGIN;

CREATE TEMP TABLE qr3a_manual_fixture_output (
    cuenta_id integer NOT NULL,
    evento_id integer NOT NULL,
    invitacion_id integer NOT NULL,
    qr_codigo text NOT NULL,
    mesa_id integer NOT NULL,
    nombre_evento text NOT NULL
) ON COMMIT PRESERVE ROWS;

DO $setup$
DECLARE
    v_cuenta_id constant integer := 2;
    v_master_auth constant uuid := '397bc597-6e61-4447-a222-dcdb55051f7b';
    v_admin_auth constant uuid := 'a3b47ae0-2824-4763-941c-4b38d9785994';
    v_operator_auth constant uuid := 'd29465aa-678c-4f00-87fb-cdaed8ea55d9';
    v_consulta_auth constant uuid := 'f85e972f-8c72-4556-a302-10b419ee5a7e';
    v_nombre_evento constant text := 'TEST QR3A MANUAL';
    v_nombre_invitacion constant text := 'TEST QR3A FAMILIA';
    v_nombre_mesa constant text := 'MESA QR3A TEST';
    v_codigo_qr constant text := 'T3A1';
    v_lugar_id integer;
    v_salon_id integer;
    v_evento_id integer;
    v_invitacion_id integer;
    v_mesa_id integer;
    v_operator_usuario uuid;
    v_consulta_usuario uuid;
    v_respuesta_qr jsonb;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtext('qr3a_manual_fixture:' || v_cuenta_id::text)
    );
    IF NOT EXISTS (
        SELECT 1 FROM public.evp_cta_cuenta
        WHERE cta_cuenta_id = v_cuenta_id AND cta_estado = 'Activo'
    ) THEN
        RAISE EXCEPTION 'QR3A_SETUP: cuenta % no existe o no esta Activa', v_cuenta_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.evp_eve_evento
        WHERE eve_cuenta_id = v_cuenta_id AND eve_nombre_evento = v_nombre_evento
    ) THEN
        RAISE EXCEPTION 'QR3A_SETUP: ya existe el fixture % en cuenta %; ejecute cleanup antes de recrearlo', v_nombre_evento, v_cuenta_id;
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr WHERE iqr_codigo = v_codigo_qr
    ) THEN
        RAISE EXCEPTION 'QR3A_SETUP: el codigo QR % ya existe; no se reutiliza', v_codigo_qr;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.evp_usr_usuario
        WHERE usr_usuario_auth_uuid = v_master_auth
          AND usr_estado = 'Activo' AND usr_es_usuario_master
    ) THEN
        RAISE EXCEPTION 'QR3A_SETUP: Master configurado no es valido';
    END IF;

    SELECT u.usr_usuario_id INTO v_operator_usuario
    FROM public.evp_usr_usuario u
    JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
    WHERE u.usr_usuario_auth_uuid = v_operator_auth AND u.usr_estado = 'Activo'
      AND r.ucu_cuenta_id = v_cuenta_id AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Operador'
      AND u.usr_cuenta_id_default IS NOT NULL AND u.usr_evento_id_default IS NOT NULL;
    IF v_operator_usuario IS NULL THEN
        RAISE EXCEPTION 'QR3A_SETUP: Operador/UCU/defaults invalidos; no se crea UEV que pueda alterar defaults';
    END IF;

    SELECT u.usr_usuario_id INTO v_consulta_usuario
    FROM public.evp_usr_usuario u
    JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
    WHERE u.usr_usuario_auth_uuid = v_consulta_auth AND u.usr_estado = 'Activo'
      AND r.ucu_cuenta_id = v_cuenta_id AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Consulta'
      AND u.usr_cuenta_id_default IS NOT NULL AND u.usr_evento_id_default IS NOT NULL;
    IF v_consulta_usuario IS NULL THEN
        RAISE EXCEPTION 'QR3A_SETUP: Consulta/UCU/defaults invalidos; no se crea UEV que pueda alterar defaults';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.evp_usr_usuario u
        JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id = u.usr_usuario_id
        WHERE u.usr_usuario_auth_uuid = v_admin_auth AND u.usr_estado = 'Activo'
          AND r.ucu_cuenta_id = v_cuenta_id AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Administrador'
    ) THEN
        RAISE EXCEPTION 'QR3A_SETUP: Administrador de cuenta 2 invalido';
    END IF;

    SELECT s.sal_lugar_id, s.sal_salon_id INTO v_lugar_id, v_salon_id
    FROM public.evp_sal_salon s
    JOIN public.evp_lug_lugar l
      ON l.lug_cuenta_id = s.sal_cuenta_id AND l.lug_lugar_id = s.sal_lugar_id
    WHERE s.sal_cuenta_id = v_cuenta_id
      AND s.sal_estado = 'Activo' AND l.lug_estado = 'Activo'
    ORDER BY s.sal_lugar_id, s.sal_salon_id
    LIMIT 1;
    IF v_lugar_id IS NULL OR v_salon_id IS NULL THEN
        RAISE EXCEPTION 'QR3A_SETUP: cuenta % no tiene lugar/salon Activo reutilizable', v_cuenta_id;
    END IF;

    INSERT INTO public.evp_eve_evento (
        eve_cuenta_id, eve_evento_id, eve_nombre_evento, eve_nombre_evento_abrev,
        eve_fase_evento, eve_tipo_evento, eve_lugar_id, eve_salon_id, eve_cant_mesas,
        eve_fecha_hora_inicio, eve_fecha_hora_fin, eve_estado
    ) VALUES (
        v_cuenta_id, NULL, v_nombre_evento, 'TQR3A',
        'En_proceso', 'Otro', v_lugar_id, v_salon_id, 1,
        pg_catalog.now() - pg_catalog.make_interval(hours => 1),
        pg_catalog.now() + pg_catalog.make_interval(hours => 4),
        'Activo'
    ) RETURNING eve_evento_id INTO v_evento_id;

    INSERT INTO public.evp_mes_mesa (
        mes_cuenta_id, mes_evento_id, mes_mesa_id, mes_nombre_mesa, mes_estado
    ) VALUES (
        v_cuenta_id, v_evento_id, NULL, v_nombre_mesa, 'Activo'
    ) RETURNING mes_mesa_id INTO v_mesa_id;

    INSERT INTO public.evp_inv_invitacion (
        inv_cuenta_id, inv_evento_id, inv_invitacion_id, inv_cod_abrev_invitacion,
        inv_destinatario_invitacion, inv_cant_puestos_reservados, inv_estado
    ) VALUES (
        v_cuenta_id, v_evento_id, NULL, 'Q3A', v_nombre_invitacion, 3, 'Activo'
    ) RETURNING inv_invitacion_id INTO v_invitacion_id;

    INSERT INTO public.evp_ivt_invitado (
        ivt_cuenta_id, ivt_evento_id, ivt_invitacion_id, ivt_invitado_id,
        ivt_nombre_invitado, ivt_es_invitado_principal, ivt_es_invitado_imprevisto,
        ivt_mesa_id, ivt_puesto_id, ivt_llegada_confirmada, ivt_estado
    ) VALUES
        (v_cuenta_id, v_evento_id, v_invitacion_id, NULL, 'QR3A Ana Test', true, false, v_mesa_id, 1, false, 'Activo'),
        (v_cuenta_id, v_evento_id, v_invitacion_id, NULL, 'QR3A Carlos Test', false, false, v_mesa_id, 2, false, 'Activo'),
        (v_cuenta_id, v_evento_id, v_invitacion_id, NULL, 'QR3A Maria Test', false, false, v_mesa_id, 3, false, 'Activo');

    -- Solo UEV del fixture: no se toca UCU. Los defaults ya se exigieron no nulos.
    INSERT INTO public.evp_uev_usuario_evento (
        uev_cuenta_id, uev_evento_id, uev_usuario_id, uev_estado
    ) VALUES
        (v_cuenta_id, v_evento_id, v_operator_usuario, 'Activo'),
        (v_cuenta_id, v_evento_id, v_consulta_usuario, 'Activo');

    -- En SQL Editor no hay JWT de cliente. Este contexto local reproduce el
    -- patrón validado por las pruebas funcionales y la RPC sigue aplicando su autorización.
    PERFORM pg_catalog.set_config('request.jwt.claim.sub', v_master_auth::text, true);
    IF auth.uid() IS DISTINCT FROM v_master_auth THEN
        RAISE EXCEPTION 'QR3A_SETUP: no fue posible establecer auth.uid() del Master para la RPC';
    END IF;
    v_respuesta_qr := public.evp_admin_crear_qr_invitacion(
        v_cuenta_id, v_evento_id, v_invitacion_id, v_codigo_qr
    );
    IF v_respuesta_qr->>'codigo_resultado' <> 'QR_CREATED' THEN
        RAISE EXCEPTION 'QR3A_SETUP: crear QR esperaba QR_CREATED, obtuvo %',
            COALESCE(v_respuesta_qr->>'codigo_resultado', 'NULL');
    END IF;

    INSERT INTO qr3a_manual_fixture_output
    VALUES (v_cuenta_id, v_evento_id, v_invitacion_id, v_codigo_qr, v_mesa_id, v_nombre_evento);
END
$setup$;

COMMIT;

SELECT cuenta_id, evento_id, invitacion_id, qr_codigo, mesa_id, nombre_evento
FROM qr3a_manual_fixture_output;

DROP TABLE qr3a_manual_fixture_output;
