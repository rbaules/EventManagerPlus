-- QR-3A cleanup persistente. Ejecutar como administrador confiable en SQL Editor.
-- Si una marca no coincide, aborta antes de borrar; ante error ejecute ROLLBACK.
BEGIN;

DO $cleanup$
DECLARE
    v_cuenta_id constant integer := 2;
    v_nombre_evento constant text := 'TEST QR3A MANUAL';
    v_nombre_invitacion constant text := 'TEST QR3A FAMILIA';
    v_nombre_mesa constant text := 'MESA QR3A TEST';
    v_codigo_qr constant text := 'T3A1';
    v_operator_auth constant uuid := 'd29465aa-678c-4f00-87fb-cdaed8ea55d9';
    v_consulta_auth constant uuid := 'f85e972f-8c72-4556-a302-10b419ee5a7e';
    v_evento_id integer;
    v_invitacion_id integer;
    v_mesa_id integer;
    v_operator_usuario uuid;
    v_consulta_usuario uuid;
BEGIN
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtext('qr3a_manual_fixture:' || v_cuenta_id::text)
    );
    SELECT eve_evento_id INTO v_evento_id
    FROM public.evp_eve_evento
    WHERE eve_cuenta_id = v_cuenta_id
      AND eve_nombre_evento = v_nombre_evento
      AND eve_nombre_evento_abrev = 'TQR3A';

    IF v_evento_id IS NULL THEN
        IF EXISTS (
            SELECT 1 FROM public.evp_eve_evento
            WHERE eve_cuenta_id = v_cuenta_id AND eve_nombre_evento = v_nombre_evento
        ) THEN
            RAISE EXCEPTION 'QR3A_CLEANUP: evento con nombre de fixture no tiene la marca TQR3A; no se borra';
        END IF;
        RAISE NOTICE 'QR3A_CLEANUP: fixture inexistente; no hay cambios';
        RETURN;
    END IF;
    IF (SELECT count(*) FROM public.evp_eve_evento
        WHERE eve_cuenta_id = v_cuenta_id AND eve_nombre_evento = v_nombre_evento) <> 1 THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: hay mas de un evento con la marca; no se borra';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.evp_usr_usuario
        WHERE usr_cuenta_id_default = v_cuenta_id AND usr_evento_id_default = v_evento_id
    ) THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: un usuario tiene este evento como default; restablezcalo manualmente antes del cleanup';
    END IF;

    SELECT inv_invitacion_id INTO v_invitacion_id
    FROM public.evp_inv_invitacion
    WHERE inv_cuenta_id = v_cuenta_id AND inv_evento_id = v_evento_id
      AND inv_destinatario_invitacion = v_nombre_invitacion
      AND inv_cod_abrev_invitacion = 'Q3A'
      AND inv_cant_puestos_reservados = 3;
    IF v_invitacion_id IS NULL OR (SELECT count(*) FROM public.evp_inv_invitacion
        WHERE inv_cuenta_id = v_cuenta_id AND inv_evento_id = v_evento_id) <> 1 THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: invitacion del fixture no coincide exactamente; no se borra';
    END IF;

    SELECT mes_mesa_id INTO v_mesa_id
    FROM public.evp_mes_mesa
    WHERE mes_cuenta_id = v_cuenta_id AND mes_evento_id = v_evento_id
      AND mes_nombre_mesa = v_nombre_mesa;
    IF v_mesa_id IS NULL OR (SELECT count(*) FROM public.evp_mes_mesa
        WHERE mes_cuenta_id = v_cuenta_id AND mes_evento_id = v_evento_id) <> 1 THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: mesa del fixture no coincide exactamente; no se borra';
    END IF;

    IF (SELECT count(*) FROM public.evp_ivt_invitado
        WHERE ivt_cuenta_id = v_cuenta_id AND ivt_evento_id = v_evento_id
          AND ivt_invitacion_id = v_invitacion_id
          AND ivt_nombre_invitado IN ('QR3A Ana Test', 'QR3A Carlos Test', 'QR3A Maria Test')
          AND ivt_mesa_id = v_mesa_id AND ivt_puesto_id IN (1, 2, 3)) <> 3
       OR EXISTS (
           SELECT 1 FROM public.evp_ivt_invitado
           WHERE ivt_cuenta_id = v_cuenta_id AND ivt_evento_id = v_evento_id
             AND ivt_invitacion_id = v_invitacion_id
             AND ivt_nombre_invitado NOT IN ('QR3A Ana Test', 'QR3A Carlos Test', 'QR3A Maria Test')
       ) THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: invitados del fixture no coinciden exactamente; no se borra';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.evp_iqr_invitacion_qr
        WHERE iqr_cuenta_id = v_cuenta_id AND iqr_evento_id = v_evento_id
          AND (iqr_invitacion_id <> v_invitacion_id OR iqr_codigo <> v_codigo_qr)
    ) THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: hay QR ajeno en el evento fixture; no se borra';
    END IF;

    SELECT usr_usuario_id INTO v_operator_usuario
    FROM public.evp_usr_usuario WHERE usr_usuario_auth_uuid = v_operator_auth;
    SELECT usr_usuario_id INTO v_consulta_usuario
    FROM public.evp_usr_usuario WHERE usr_usuario_auth_uuid = v_consulta_auth;
    IF v_operator_usuario IS NULL OR v_consulta_usuario IS NULL OR EXISTS (
        SELECT 1 FROM public.evp_uev_usuario_evento
        WHERE uev_cuenta_id = v_cuenta_id AND uev_evento_id = v_evento_id
          AND uev_usuario_id NOT IN (v_operator_usuario, v_consulta_usuario)
    ) THEN
        RAISE EXCEPTION 'QR3A_CLEANUP: UEV del fixture no coincide exactamente; no se borra';
    END IF;

    DELETE FROM public.evp_iqr_invitacion_qr
    WHERE iqr_cuenta_id = v_cuenta_id AND iqr_evento_id = v_evento_id
      AND iqr_invitacion_id = v_invitacion_id AND iqr_codigo = v_codigo_qr;
    DELETE FROM public.evp_uev_usuario_evento
    WHERE uev_cuenta_id = v_cuenta_id AND uev_evento_id = v_evento_id
      AND uev_usuario_id IN (v_operator_usuario, v_consulta_usuario);
    DELETE FROM public.evp_ivt_invitado
    WHERE ivt_cuenta_id = v_cuenta_id AND ivt_evento_id = v_evento_id
      AND ivt_invitacion_id = v_invitacion_id
      AND ivt_nombre_invitado IN ('QR3A Ana Test', 'QR3A Carlos Test', 'QR3A Maria Test')
      AND ivt_mesa_id = v_mesa_id AND ivt_puesto_id IN (1, 2, 3);
    DELETE FROM public.evp_inv_invitacion
    WHERE inv_cuenta_id = v_cuenta_id AND inv_evento_id = v_evento_id
      AND inv_invitacion_id = v_invitacion_id
      AND inv_destinatario_invitacion = v_nombre_invitacion AND inv_cod_abrev_invitacion = 'Q3A';
    DELETE FROM public.evp_mes_mesa
    WHERE mes_cuenta_id = v_cuenta_id AND mes_evento_id = v_evento_id
      AND mes_mesa_id = v_mesa_id AND mes_nombre_mesa = v_nombre_mesa;
    DELETE FROM public.evp_eve_evento
    WHERE eve_cuenta_id = v_cuenta_id AND eve_evento_id = v_evento_id
      AND eve_nombre_evento = v_nombre_evento AND eve_nombre_evento_abrev = 'TQR3A';
END
$cleanup$;

COMMIT;

SELECT 'PASS' AS qr3a_manual_fixture_cleanup;
