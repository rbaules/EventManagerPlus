-- QR-2A: resolucion autenticada de QR externo para check-in.
CREATE FUNCTION public.evp_oper_resolver_invitacion_qr(
    p_cuenta_id integer, p_evento_id integer, p_codigo text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_qr public.evp_iqr_invitacion_qr%ROWTYPE;
    v_invitacion public.evp_inv_invitacion%ROWTYPE;
    v_codigo text;
    v_mesa_id integer;
    v_mesa_nombre text;
    v_invitados_activos integer;
BEGIN
    SELECT * INTO v_actor FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED'); END IF;
    IF NOT v_actor.usr_es_usuario_master AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta r
        WHERE r.ucu_usuario_id = v_actor.usr_usuario_id AND r.ucu_cuenta_id = p_cuenta_id
          AND r.ucu_estado = 'Activo' AND r.ucu_rol = 'Administrador'
    ) AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta r JOIN public.evp_uev_usuario_evento e
          ON e.uev_usuario_id = r.ucu_usuario_id AND e.uev_cuenta_id = p_cuenta_id AND e.uev_evento_id = p_evento_id
        WHERE r.ucu_usuario_id = v_actor.usr_usuario_id AND r.ucu_cuenta_id = p_cuenta_id
          AND r.ucu_estado = 'Activo' AND r.ucu_rol IN ('Operador', 'Consulta') AND e.uev_estado = 'Activo'
    ) THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_ALLOWED'); END IF;
    v_codigo := pg_catalog.upper(pg_catalog.btrim(p_codigo));
    IF v_codigo IS NULL OR v_codigo !~ '^[A-Z0-9]{4}$' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_INVALID_FORMAT'); END IF;
    SELECT * INTO v_cuenta FROM public.evp_cta_cuenta WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND OR v_cuenta.cta_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_AVAILABLE'); END IF;
    SELECT * INTO v_evento FROM public.evp_eve_evento WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND OR v_evento.eve_estado <> 'Activo' OR v_evento.eve_fase_evento <> 'En_proceso' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_AVAILABLE'); END IF;
    SELECT * INTO v_qr FROM public.evp_iqr_invitacion_qr WHERE iqr_cuenta_id = p_cuenta_id
      AND iqr_evento_id = p_evento_id AND iqr_codigo = v_codigo;
    IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_FOUND'); END IF;
    IF v_qr.iqr_estado <> 'Activo' OR v_qr.iqr_fecha_revocacion IS NOT NULL THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_REVOKED'); END IF;
    IF pg_catalog.now() < v_qr.iqr_valido_desde OR pg_catalog.now() > v_qr.iqr_valido_hasta THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_AVAILABLE'); END IF;
    SELECT * INTO v_invitacion FROM public.evp_inv_invitacion WHERE inv_cuenta_id = p_cuenta_id
      AND inv_evento_id = p_evento_id AND inv_invitacion_id = v_qr.iqr_invitacion_id;
    IF NOT FOUND OR v_invitacion.inv_estado <> 'Activo' THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_NOT_AVAILABLE'); END IF;
    SELECT i.ivt_mesa_id, m.mes_nombre_mesa, pg_catalog.count(*) INTO v_mesa_id, v_mesa_nombre, v_invitados_activos
    FROM public.evp_ivt_invitado i LEFT JOIN public.evp_mes_mesa m ON m.mes_cuenta_id=i.ivt_cuenta_id AND m.mes_evento_id=i.ivt_evento_id AND m.mes_mesa_id=i.ivt_mesa_id
    WHERE i.ivt_cuenta_id=p_cuenta_id AND i.ivt_evento_id=p_evento_id AND i.ivt_invitacion_id=v_invitacion.inv_invitacion_id AND i.ivt_estado='Activo'
    GROUP BY i.ivt_mesa_id, m.mes_nombre_mesa ORDER BY i.ivt_mesa_id NULLS LAST LIMIT 1;
    RETURN pg_catalog.jsonb_build_object('ok', true, 'codigo_resultado', 'QR_RESOLVED', 'cuenta_id', p_cuenta_id,
      'evento_id', p_evento_id, 'invitacion_id', v_invitacion.inv_invitacion_id,
      'destinatario', v_invitacion.inv_destinatario_invitacion, 'puestos_reservados', v_invitacion.inv_cant_puestos_reservados,
      'mesa_id', v_mesa_id, 'mesa_nombre', v_mesa_nombre, 'invitados_activos', coalesce(v_invitados_activos, 0));
EXCEPTION WHEN OTHERS THEN RETURN pg_catalog.jsonb_build_object('ok', false, 'codigo_resultado', 'QR_OPERATION_ERROR'); END;
$function$;
ALTER FUNCTION public.evp_oper_resolver_invitacion_qr(integer, integer, text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.evp_oper_resolver_invitacion_qr(integer, integer, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.evp_oper_resolver_invitacion_qr(integer, integer, text) TO authenticated;
