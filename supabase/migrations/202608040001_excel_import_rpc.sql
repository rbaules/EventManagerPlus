-- EventPlus 7C: importación inicial atómica de mesas, invitaciones e invitados.
CREATE OR REPLACE FUNCTION public.evp_importar_evento_desde_json(
    p_cuenta_id integer,
    p_evento_id integer,
    p_payload jsonb,
    p_payload_hash text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $function$
DECLARE
    v_usuario public.evp_usr_usuario%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_mesa jsonb;
    v_invitacion jsonb;
    v_invitado jsonb;
    v_table_map jsonb := '{}'::jsonb;
    v_table_names jsonb := '{}'::jsonb;
    v_invitation_codes jsonb := '{}'::jsonb;
    v_guest_names jsonb := '{}'::jsonb;
    v_orders jsonb;
    v_code text;
    v_name text;
    v_normalized text;
    v_recipient text;
    v_table_code text;
    v_email text;
    v_phone text;
    v_order integer;
    v_table_id integer;
    v_invitation_id integer;
    v_primary_count integer;
    v_guest_count integer;
    v_tables_created integer := 0;
    v_invitations_created integer := 0;
    v_guests_created integer := 0;
    v_constraint_name text;
BEGIN
    IF auth.uid() IS NULL THEN
        RAISE EXCEPTION USING MESSAGE = 'IMPORT_FORBIDDEN';
    END IF;
    SELECT * INTO v_usuario
    FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN RAISE EXCEPTION USING MESSAGE = 'IMPORT_FORBIDDEN'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.evp_cta_cuenta WHERE cta_cuenta_id=p_cuenta_id AND cta_estado='Activo')
    THEN RAISE EXCEPTION USING MESSAGE = 'IMPORT_FORBIDDEN'; END IF;

    -- Administrador activo accede a todos los eventos de su cuenta.
    -- Solo Operador/Consulta dependen de evp_uev_usuario_evento.
    IF NOT coalesce(v_usuario.usr_es_usuario_master, false) AND NOT EXISTS (
        SELECT 1 FROM public.evp_ucu_usuario_cuenta ucu
        JOIN public.evp_cta_cuenta cta ON cta.cta_cuenta_id = ucu.ucu_cuenta_id
        WHERE ucu.ucu_usuario_id = v_usuario.usr_usuario_id
          AND ucu.ucu_cuenta_id = p_cuenta_id
          AND ucu.ucu_estado = 'Activo' AND ucu.ucu_rol = 'Administrador'
          AND cta.cta_estado = 'Activo'
    ) THEN RAISE EXCEPTION USING MESSAGE = 'IMPORT_FORBIDDEN'; END IF;

    IF NOT pg_try_advisory_xact_lock(p_cuenta_id, p_evento_id) THEN
        RAISE EXCEPTION USING MESSAGE = 'CONCURRENT_IMPORT';
    END IF;
    SELECT * INTO v_evento FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION USING MESSAGE = 'EVENT_NOT_FOUND'; END IF;
    IF v_evento.eve_estado <> 'Activo' THEN RAISE EXCEPTION USING MESSAGE = 'EVENT_NOT_ACTIVE'; END IF;
    IF v_evento.eve_fase_evento <> 'Pre_evento' THEN RAISE EXCEPTION USING MESSAGE = 'EVENT_NOT_PRE_EVENT'; END IF;
    IF EXISTS (SELECT 1 FROM public.evp_mes_mesa WHERE mes_cuenta_id=p_cuenta_id AND mes_evento_id=p_evento_id)
       OR EXISTS (SELECT 1 FROM public.evp_inv_invitacion WHERE inv_cuenta_id=p_cuenta_id AND inv_evento_id=p_evento_id)
       OR EXISTS (SELECT 1 FROM public.evp_ivt_invitado WHERE ivt_cuenta_id=p_cuenta_id AND ivt_evento_id=p_evento_id)
    THEN RAISE EXCEPTION USING MESSAGE = 'EVENT_NOT_EMPTY'; END IF;

    IF p_payload IS NULL OR jsonb_typeof(p_payload) <> 'object'
       OR p_payload->>'version' <> '1'
       OR jsonb_typeof(p_payload->'mesas') <> 'array'
       OR jsonb_typeof(p_payload->'invitaciones') <> 'array'
       OR coalesce(p_payload_hash,'') !~ '^[0-9a-f]{64}$'
       OR octet_length(p_payload::text) > 10485760
       OR jsonb_array_length(p_payload->'invitaciones') = 0
    THEN RAISE EXCEPTION USING MESSAGE = 'INVALID_PAYLOAD'; END IF;

    FOR v_mesa IN SELECT value FROM jsonb_array_elements(p_payload->'mesas') LOOP
        IF jsonb_typeof(v_mesa) <> 'object' THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
        v_code := btrim(coalesce(v_mesa->>'codigo_externo',''));
        v_name := btrim(coalesce(v_mesa->>'nombre',''));
        v_normalized := public.evp_normalizar_texto(v_name);
        IF v_code = '' OR length(v_code)>50 OR v_name='' OR length(v_name)>30
           OR v_normalized IS NULL OR v_normalized = ''
           OR v_table_map ? v_code OR v_table_names ? v_normalized
        THEN RAISE EXCEPTION USING MESSAGE = 'INVALID_PAYLOAD'; END IF;
        INSERT INTO public.evp_mes_mesa(mes_cuenta_id,mes_evento_id,mes_nombre_mesa,mes_estado)
        VALUES(p_cuenta_id,p_evento_id,v_name,'Activo') RETURNING mes_mesa_id INTO v_table_id;
        v_table_map := v_table_map || jsonb_build_object(v_code,v_table_id);
        v_table_names := v_table_names || jsonb_build_object(v_normalized,v_code);
        v_tables_created := v_tables_created + 1;
    END LOOP;
    IF v_evento.eve_cant_mesas IS NOT NULL AND v_tables_created > v_evento.eve_cant_mesas
    THEN RAISE EXCEPTION USING MESSAGE = 'INVALID_PAYLOAD'; END IF;

    FOR v_invitacion IN SELECT value FROM jsonb_array_elements(p_payload->'invitaciones') LOOP
        IF jsonb_typeof(v_invitacion) <> 'object' THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
        v_code := btrim(coalesce(v_invitacion->>'codigo_externo',''));
        v_recipient := btrim(coalesce(v_invitacion->>'destinatario',''));
        IF jsonb_typeof(v_invitacion->'invitados') <> 'array' THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
        v_guest_count := jsonb_array_length(v_invitacion->'invitados');
        SELECT count(*) INTO v_primary_count FROM jsonb_array_elements(v_invitacion->'invitados') g WHERE g->'es_principal' = 'true'::jsonb;
        IF v_guests_created + v_guest_count > 5000 OR v_code='' OR length(v_code)>50 OR v_invitation_codes ? v_code
           OR v_recipient='' OR length(v_recipient)>100 OR v_guest_count=0
           OR v_primary_count<>1 OR (v_invitacion->>'puestos_reservados') IS NULL
           OR (v_invitacion->>'puestos_reservados') !~ '^\d+$'
           OR length(v_invitacion->>'puestos_reservados') > 6
           OR (v_invitacion->>'puestos_reservados')::integer <> v_guest_count
        THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
        v_invitation_codes := v_invitation_codes || jsonb_build_object(v_code,true);
        INSERT INTO public.evp_inv_invitacion(inv_cuenta_id,inv_evento_id,inv_destinatario_invitacion,inv_cant_puestos_reservados,inv_estado)
        VALUES(p_cuenta_id,p_evento_id,v_recipient,v_guest_count,'Activo') RETURNING inv_invitacion_id INTO v_invitation_id;
        v_invitations_created := v_invitations_created + 1;
        v_orders := '{}'::jsonb;
        FOR v_invitado IN SELECT value FROM jsonb_array_elements(v_invitacion->'invitados') LOOP
            IF jsonb_typeof(v_invitado) <> 'object' THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
            IF jsonb_typeof(v_invitado->'orden') <> 'number' OR (v_invitado->>'orden') !~ '^\d+$'
               OR length(v_invitado->>'orden') > 9
            THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
            v_order := (v_invitado->>'orden')::integer;
            v_name := btrim(coalesce(v_invitado->>'nombre',''));
            v_normalized := public.evp_normalizar_texto(v_name);
            v_phone := nullif(btrim(coalesce(v_invitado->>'telefono','')),'');
            v_email := nullif(lower(btrim(coalesce(v_invitado->>'email',''))),'');
            v_table_code := nullif(btrim(coalesce(v_invitado->>'mesa_codigo','')),'');
            IF jsonb_typeof(v_invitado->'es_principal') <> 'boolean'
               OR v_order<=0 OR v_orders ? v_order::text OR v_name='' OR length(v_name)>80
               OR v_normalized IS NULL OR v_normalized = ''
               OR length(coalesce(v_phone,''))>20
               OR length(coalesce(v_email,''))>254
               OR (v_email IS NOT NULL AND v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$')
            THEN RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD'; END IF;
            IF v_guest_names ? v_normalized THEN RAISE EXCEPTION USING MESSAGE='DUPLICATE_GUEST'; END IF;
            IF v_table_code IS NOT NULL AND NOT (v_table_map ? v_table_code)
            THEN RAISE EXCEPTION USING MESSAGE='INVALID_TABLE_REFERENCE'; END IF;
            v_orders := v_orders || jsonb_build_object(v_order::text,true);
            v_guest_names := v_guest_names || jsonb_build_object(v_normalized,true);
            v_table_id := CASE WHEN v_table_code IS NULL THEN NULL ELSE (v_table_map->>v_table_code)::integer END;
            INSERT INTO public.evp_ivt_invitado(
                ivt_cuenta_id,ivt_evento_id,ivt_invitacion_id,ivt_nombre_invitado,
                ivt_es_invitado_principal,ivt_es_invitado_imprevisto,ivt_email,ivt_telefono,
                ivt_mesa_id,ivt_puesto_id,ivt_llegada_confirmada,ivt_tiene_novedad,
                ivt_invitado_creado_por,ivt_estado
            ) VALUES (
                p_cuenta_id,p_evento_id,v_invitation_id,v_name,
                (v_invitado->>'es_principal')::boolean,false,v_email,v_phone,
                v_table_id,NULL,false,false,v_usuario.usr_usuario_id,'Activo'
            );
            v_guests_created := v_guests_created + 1;
        END LOOP;
    END LOOP;
    RETURN jsonb_build_object('ok',true,'cuenta_id',p_cuenta_id,'evento_id',p_evento_id,
        'mesas_creadas',v_tables_created,'invitaciones_creadas',v_invitations_created,'invitados_creados',v_guests_created);
EXCEPTION
    WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;
        IF v_constraint_name = 'ux_evp_ivt_nombre_evento_activo' THEN
            RAISE EXCEPTION USING MESSAGE='DUPLICATE_GUEST';
        END IF;
        RAISE EXCEPTION USING MESSAGE='IMPORT_INTERNAL_ERROR';
    WHEN foreign_key_violation THEN
        GET STACKED DIAGNOSTICS v_constraint_name = CONSTRAINT_NAME;
        IF v_constraint_name = 'fk_ivt_mesa' THEN
            RAISE EXCEPTION USING MESSAGE='INVALID_TABLE_REFERENCE';
        END IF;
        RAISE EXCEPTION USING MESSAGE='IMPORT_INTERNAL_ERROR';
    WHEN check_violation OR not_null_violation OR invalid_text_representation OR numeric_value_out_of_range THEN
        RAISE EXCEPTION USING MESSAGE='INVALID_PAYLOAD';
    WHEN OTHERS THEN
        IF SQLERRM = ANY (ARRAY[
            'IMPORT_FORBIDDEN','EVENT_NOT_FOUND','EVENT_NOT_ACTIVE','EVENT_NOT_PRE_EVENT',
            'EVENT_NOT_EMPTY','INVALID_PAYLOAD','DUPLICATE_GUEST',
            'INVALID_TABLE_REFERENCE','CONCURRENT_IMPORT','IMPORT_INTERNAL_ERROR'
        ]) THEN
            RAISE;
        END IF;
        RAISE EXCEPTION USING MESSAGE='IMPORT_INTERNAL_ERROR';
END;
$function$;

REVOKE ALL ON FUNCTION public.evp_importar_evento_desde_json(integer,integer,jsonb,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_importar_evento_desde_json(integer,integer,jsonb,text) FROM anon;
GRANT EXECUTE ON FUNCTION public.evp_importar_evento_desde_json(integer,integer,jsonb,text) TO authenticated;
