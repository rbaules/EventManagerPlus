-- EventPlus: registro, edición y limpieza segura de novedades de invitados.
-- No concede UPDATE directo sobre evp_ivt_invitado.
CREATE OR REPLACE FUNCTION public.evp_admin_guardar_novedad_invitado(
    p_invitado_uuid uuid,
    p_descripcion text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_auth_uid uuid := auth.uid();
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_invitado public.evp_ivt_invitado%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_descripcion text := nullif(pg_catalog.btrim(p_descripcion), '');
    v_es_admin boolean := false;
    v_es_operador boolean := false;
    v_es_consulta boolean := false;
    v_hay_historial boolean;
BEGIN
    IF v_auth_uid IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'UNAUTHENTICATED');
    END IF;

    SELECT * INTO v_actor
    FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = v_auth_uid;

    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'ACTOR_NOT_FOUND');
    END IF;
    IF v_actor.usr_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'ACTOR_INACTIVE');
    END IF;
    IF p_invitado_uuid IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'INVITADO_NOT_FOUND');
    END IF;
    IF pg_catalog.char_length(coalesce(v_descripcion, '')) > 200 THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'DESCRIPTION_TOO_LONG');
    END IF;

    SELECT * INTO v_invitado
    FROM public.evp_ivt_invitado
    WHERE ivt_invitado_uuid = p_invitado_uuid
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'INVITADO_NOT_FOUND');
    END IF;

    SELECT * INTO v_evento
    FROM public.evp_eve_evento
    WHERE eve_cuenta_id = v_invitado.ivt_cuenta_id
      AND eve_evento_id = v_invitado.ivt_evento_id;
    IF NOT FOUND OR v_evento.eve_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'EVENTO_INACTIVE');
    END IF;

    SELECT * INTO v_cuenta
    FROM public.evp_cta_cuenta
    WHERE cta_cuenta_id = v_evento.eve_cuenta_id;
    IF NOT FOUND OR v_cuenta.cta_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'CUENTA_INACTIVE');
    END IF;

    IF v_evento.eve_fase_evento NOT IN ('Pre_evento', 'En_proceso') THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'EVENT_PHASE_READ_ONLY');
    END IF;

    IF NOT v_actor.usr_es_usuario_master THEN
        SELECT
            coalesce(pg_catalog.bool_or(ucu_rol = 'Administrador'), false),
            coalesce(pg_catalog.bool_or(ucu_rol = 'Operador'), false),
            coalesce(pg_catalog.bool_or(ucu_rol = 'Consulta'), false)
        INTO v_es_admin, v_es_operador, v_es_consulta
        FROM public.evp_ucu_usuario_cuenta
        WHERE ucu_usuario_id = v_actor.usr_usuario_id
          AND ucu_cuenta_id = v_invitado.ivt_cuenta_id
          AND ucu_estado = 'Activo';

        IF v_es_consulta AND NOT v_es_admin AND NOT v_es_operador THEN
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'CONSULTA_READ_ONLY');
        END IF;

        IF v_es_operador AND NOT v_es_admin THEN
            v_es_operador := EXISTS (
                SELECT 1
                FROM public.evp_uev_usuario_evento
                WHERE uev_usuario_id = v_actor.usr_usuario_id
                  AND uev_cuenta_id = v_invitado.ivt_cuenta_id
                  AND uev_evento_id = v_invitado.ivt_evento_id
                  AND uev_estado = 'Activo'
            );
        END IF;

        IF NOT v_es_admin AND NOT v_es_operador THEN
            RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo', 'FORBIDDEN');
        END IF;
    END IF;

    v_hay_historial := v_invitado.ivt_novedad_creada IS NOT NULL
        OR v_invitado.ivt_novedad_creada_por IS NOT NULL;

    UPDATE public.evp_ivt_invitado
    SET
        ivt_tiene_novedad = (v_descripcion IS NOT NULL),
        ivt_descripcion_novedad = v_descripcion,
        ivt_novedad_creada = CASE
            WHEN v_descripcion IS NOT NULL AND NOT v_hay_historial
                THEN pg_catalog.clock_timestamp()
            ELSE ivt_novedad_creada
        END,
        ivt_novedad_creada_por = CASE
            WHEN v_descripcion IS NOT NULL AND NOT v_hay_historial
                THEN v_actor.usr_usuario_id
            ELSE ivt_novedad_creada_por
        END,
        ivt_novedad_mod = CASE
            WHEN v_hay_historial THEN pg_catalog.clock_timestamp()
            ELSE ivt_novedad_mod
        END,
        ivt_novedad_mod_por = CASE
            WHEN v_hay_historial THEN v_actor.usr_usuario_id
            ELSE ivt_novedad_mod_por
        END,
        ivt_invitado_mod_por = v_actor.usr_usuario_id
    WHERE ivt_cuenta_id = v_invitado.ivt_cuenta_id
      AND ivt_evento_id = v_invitado.ivt_evento_id
      AND ivt_invitacion_id = v_invitado.ivt_invitacion_id
      AND ivt_invitado_id = v_invitado.ivt_invitado_id
    RETURNING * INTO v_invitado;

    RETURN pg_catalog.jsonb_build_object(
        'ok', true,
        'codigo', 'OK',
        'tiene_novedad', v_invitado.ivt_tiene_novedad,
        'descripcion', v_invitado.ivt_descripcion_novedad,
        'novedad_creada', v_invitado.ivt_novedad_creada,
        'novedad_modificada', v_invitado.ivt_novedad_mod
    );
END;
$function$;

ALTER FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM anon;
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) TO authenticated;
