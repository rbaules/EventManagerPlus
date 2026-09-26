-- EventPlus QR-1C-B1: administracion segura del QR de invitaciones.
CREATE OR REPLACE FUNCTION public.evp_admin_obtener_qr_invitacion(
    p_cuenta_id integer,
    p_evento_id integer,
    p_invitacion_id integer
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_invitacion public.evp_inv_invitacion%ROWTYPE;
    v_qr public.evp_iqr_invitacion_qr%ROWTYPE;
BEGIN
    SELECT * INTO v_actor
    FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid()
      AND usr_estado = 'Activo';
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED');
    END IF;
    IF NOT v_actor.usr_es_usuario_master AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta
        WHERE ucu_usuario_id = v_actor.usr_usuario_id
          AND ucu_cuenta_id = p_cuenta_id
          AND ucu_estado = 'Activo'
          AND ucu_rol = 'Administrador'
    ) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED');
    END IF;

    SELECT * INTO v_cuenta FROM public.evp_cta_cuenta
    WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_NOT_FOUND');
    END IF;
    IF v_cuenta.cta_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_INACTIVE');
    END IF;

    SELECT * INTO v_evento FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_NOT_FOUND');
    END IF;
    IF v_evento.eve_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_INACTIVE');
    END IF;

    SELECT * INTO v_invitacion FROM public.evp_inv_invitacion
    WHERE inv_cuenta_id = p_cuenta_id
      AND inv_evento_id = p_evento_id
      AND inv_invitacion_id = p_invitacion_id;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_NOT_FOUND');
    END IF;
    IF v_invitacion.inv_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_INACTIVE');
    END IF;

    SELECT * INTO v_qr FROM public.evp_iqr_invitacion_qr
    WHERE iqr_cuenta_id = p_cuenta_id
      AND iqr_evento_id = p_evento_id
      AND iqr_invitacion_id = p_invitacion_id
      AND iqr_estado = 'Activo';
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_FOUND');
    END IF;

    RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'codigo_resultado', 'QR_FOUND', 'estado', 'found',
        'cuenta_id', p_cuenta_id, 'evento_id', p_evento_id,
        'invitacion_id', p_invitacion_id, 'codigo', v_qr.iqr_codigo,
        'valido_desde', v_qr.iqr_valido_desde, 'valido_hasta', v_qr.iqr_valido_hasta
    );
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
END;
$function$;

CREATE OR REPLACE FUNCTION public.evp_admin_crear_qr_invitacion(
    p_cuenta_id integer,
    p_evento_id integer,
    p_invitacion_id integer,
    p_codigo text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_invitacion public.evp_inv_invitacion%ROWTYPE;
    v_qr public.evp_iqr_invitacion_qr%ROWTYPE;
    v_valido_desde timestamp with time zone;
    v_valido_hasta timestamp with time zone;
    v_constraint_name text;
BEGIN
    SELECT * INTO v_actor FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED');
    END IF;
    IF NOT v_actor.usr_es_usuario_master AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta
        WHERE ucu_usuario_id = v_actor.usr_usuario_id
          AND ucu_cuenta_id = p_cuenta_id
          AND ucu_estado = 'Activo' AND ucu_rol = 'Administrador'
    ) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED');
    END IF;

    SELECT * INTO v_cuenta FROM public.evp_cta_cuenta WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_NOT_FOUND'); END IF;
    IF v_cuenta.cta_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_INACTIVE'); END IF;

    SELECT * INTO v_evento FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_NOT_FOUND'); END IF;
    IF v_evento.eve_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_INACTIVE'); END IF;
    IF v_evento.eve_fase_evento NOT IN ('Pre_evento', 'En_proceso') THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_PHASE_NOT_ALLOWED');
    END IF;
    IF v_evento.eve_fecha_hora_inicio IS NULL OR v_evento.eve_fecha_hora_fin IS NULL
       OR v_evento.eve_fecha_hora_fin <= v_evento.eve_fecha_hora_inicio THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_SCHEDULE_INVALID');
    END IF;
    v_valido_desde := v_evento.eve_fecha_hora_inicio - pg_catalog.make_interval(hours => 8);
    v_valido_hasta := v_evento.eve_fecha_hora_fin + pg_catalog.make_interval(hours => 4);

    SELECT * INTO v_invitacion FROM public.evp_inv_invitacion
    WHERE inv_cuenta_id = p_cuenta_id AND inv_evento_id = p_evento_id
      AND inv_invitacion_id = p_invitacion_id
    FOR UPDATE;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_NOT_FOUND'); END IF;
    IF v_invitacion.inv_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_INACTIVE'); END IF;

    SELECT * INTO v_qr FROM public.evp_iqr_invitacion_qr
    WHERE iqr_cuenta_id = p_cuenta_id AND iqr_evento_id = p_evento_id
      AND iqr_invitacion_id = p_invitacion_id AND iqr_estado = 'Activo';
    IF FOUND THEN
        RETURN pg_catalog.jsonb_build_object(
            'ok', true, 'codigo_resultado', 'QR_ALREADY_EXISTS', 'estado', 'existing',
            'cuenta_id', p_cuenta_id, 'evento_id', p_evento_id,
            'invitacion_id', p_invitacion_id, 'codigo', v_qr.iqr_codigo,
            'valido_desde', v_qr.iqr_valido_desde, 'valido_hasta', v_qr.iqr_valido_hasta
        );
    END IF;
    IF p_codigo IS NULL OR p_codigo !~ '^[A-Z0-9]{4}$' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVALID_FORMAT');
    END IF;

    BEGIN
        INSERT INTO public.evp_iqr_invitacion_qr (
            iqr_cuenta_id, iqr_evento_id, iqr_invitacion_id, iqr_codigo,
            iqr_estado, iqr_valido_desde, iqr_valido_hasta
        ) VALUES (
            p_cuenta_id, p_evento_id, p_invitacion_id, p_codigo,
            'Activo', v_valido_desde, v_valido_hasta
        ) RETURNING * INTO v_qr;
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;
            IF v_constraint_name = 'uq_evp_iqr_cuenta_evento_codigo' THEN
                RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_CODE_CONFLICT');
            END IF;
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
        WHEN OTHERS THEN
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
    END;

    RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'codigo_resultado', 'QR_CREATED', 'estado', 'created',
        'cuenta_id', p_cuenta_id, 'evento_id', p_evento_id,
        'invitacion_id', p_invitacion_id, 'codigo', v_qr.iqr_codigo,
        'valido_desde', v_qr.iqr_valido_desde, 'valido_hasta', v_qr.iqr_valido_hasta
    );
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
END;
$function$;

CREATE OR REPLACE FUNCTION public.evp_admin_regenerar_qr_invitacion(
    p_cuenta_id integer,
    p_evento_id integer,
    p_invitacion_id integer,
    p_codigo text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_invitacion public.evp_inv_invitacion%ROWTYPE;
    v_qr_anterior public.evp_iqr_invitacion_qr%ROWTYPE;
    v_qr_nuevo public.evp_iqr_invitacion_qr%ROWTYPE;
    v_valido_desde timestamp with time zone;
    v_valido_hasta timestamp with time zone;
    v_constraint_name text;
BEGIN
    SELECT * INTO v_actor FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED'); END IF;
    IF NOT v_actor.usr_es_usuario_master AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta
        WHERE ucu_usuario_id = v_actor.usr_usuario_id
          AND ucu_cuenta_id = p_cuenta_id
          AND ucu_estado = 'Activo' AND ucu_rol = 'Administrador'
    ) THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED'); END IF;

    SELECT * INTO v_cuenta FROM public.evp_cta_cuenta WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_NOT_FOUND'); END IF;
    IF v_cuenta.cta_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_ACCOUNT_INACTIVE'); END IF;
    SELECT * INTO v_evento FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_NOT_FOUND'); END IF;
    IF v_evento.eve_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_INACTIVE'); END IF;
    IF v_evento.eve_fase_evento NOT IN ('Pre_evento', 'En_proceso') THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_PHASE_NOT_ALLOWED');
    END IF;
    IF v_evento.eve_fecha_hora_inicio IS NULL OR v_evento.eve_fecha_hora_fin IS NULL
       OR v_evento.eve_fecha_hora_fin <= v_evento.eve_fecha_hora_inicio THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_EVENT_SCHEDULE_INVALID');
    END IF;
    v_valido_desde := v_evento.eve_fecha_hora_inicio - pg_catalog.make_interval(hours => 8);
    v_valido_hasta := v_evento.eve_fecha_hora_fin + pg_catalog.make_interval(hours => 4);

    SELECT * INTO v_invitacion FROM public.evp_inv_invitacion
    WHERE inv_cuenta_id = p_cuenta_id AND inv_evento_id = p_evento_id
      AND inv_invitacion_id = p_invitacion_id
    FOR UPDATE;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_NOT_FOUND'); END IF;
    IF v_invitacion.inv_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVITATION_INACTIVE'); END IF;
    IF p_codigo IS NULL OR p_codigo !~ '^[A-Z0-9]{4}$' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVALID_FORMAT');
    END IF;

    SELECT * INTO v_qr_anterior FROM public.evp_iqr_invitacion_qr
    WHERE iqr_cuenta_id = p_cuenta_id AND iqr_evento_id = p_evento_id
      AND iqr_invitacion_id = p_invitacion_id AND iqr_estado = 'Activo';
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_FOUND'); END IF;

    BEGIN
        UPDATE public.evp_iqr_invitacion_qr
        SET iqr_estado = 'Revocado', iqr_fecha_revocacion = pg_catalog.now()
        WHERE iqr_invitacion_qr_uuid = v_qr_anterior.iqr_invitacion_qr_uuid;

        INSERT INTO public.evp_iqr_invitacion_qr (
            iqr_cuenta_id, iqr_evento_id, iqr_invitacion_id, iqr_codigo,
            iqr_estado, iqr_valido_desde, iqr_valido_hasta
        ) VALUES (
            p_cuenta_id, p_evento_id, p_invitacion_id, p_codigo,
            'Activo', v_valido_desde, v_valido_hasta
        ) RETURNING * INTO v_qr_nuevo;
    EXCEPTION
        WHEN unique_violation THEN
            GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;
            IF v_constraint_name = 'uq_evp_iqr_cuenta_evento_codigo' THEN
                RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_CODE_CONFLICT');
            END IF;
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
        WHEN OTHERS THEN
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
    END;

    RETURN pg_catalog.jsonb_build_object(
        'ok', true, 'codigo_resultado', 'QR_REGENERATED', 'estado', 'regenerated',
        'cuenta_id', p_cuenta_id, 'evento_id', p_evento_id,
        'invitacion_id', p_invitacion_id, 'codigo', v_qr_nuevo.iqr_codigo,
        'valido_desde', v_qr_nuevo.iqr_valido_desde, 'valido_hasta', v_qr_nuevo.iqr_valido_hasta
    );
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR');
END;
$function$;

ALTER FUNCTION public.evp_admin_obtener_qr_invitacion(integer, integer, integer) OWNER TO postgres;
ALTER FUNCTION public.evp_admin_crear_qr_invitacion(integer, integer, integer, text) OWNER TO postgres;
ALTER FUNCTION public.evp_admin_regenerar_qr_invitacion(integer, integer, integer, text) OWNER TO postgres;

REVOKE ALL ON FUNCTION public.evp_admin_obtener_qr_invitacion(integer, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_admin_obtener_qr_invitacion(integer, integer, integer) FROM anon;
REVOKE ALL ON FUNCTION public.evp_admin_obtener_qr_invitacion(integer, integer, integer) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.evp_admin_obtener_qr_invitacion(integer, integer, integer) TO authenticated;

REVOKE ALL ON FUNCTION public.evp_admin_crear_qr_invitacion(integer, integer, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_admin_crear_qr_invitacion(integer, integer, integer, text) FROM anon;
REVOKE ALL ON FUNCTION public.evp_admin_crear_qr_invitacion(integer, integer, integer, text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.evp_admin_crear_qr_invitacion(integer, integer, integer, text) TO authenticated;

REVOKE ALL ON FUNCTION public.evp_admin_regenerar_qr_invitacion(integer, integer, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_admin_regenerar_qr_invitacion(integer, integer, integer, text) FROM anon;
REVOKE ALL ON FUNCTION public.evp_admin_regenerar_qr_invitacion(integer, integer, integer, text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.evp_admin_regenerar_qr_invitacion(integer, integer, integer, text) TO authenticated;
