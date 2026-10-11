-- KIOSK-INDEPENDENT-0E1: PIN administrativo local por cuenta y evento.
-- El PIN nunca se persiste ni se devuelve en texto plano. bcrypt cost 12 se
-- eligio por ser un secreto de baja frecuencia y para elevar el costo de fuerza
-- bruta; el rate limit persistente queda pendiente de una fase posterior.

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

CREATE TABLE public.evp_kpa_kiosco_pin_administrativo (
    kpa_cuenta_id integer NOT NULL,
    kpa_evento_id integer NOT NULL,
    kpa_pin_hash text NOT NULL,
    kpa_estado character varying(15) NOT NULL DEFAULT 'Activo'::character varying,
    kpa_fecha_creacion timestamp with time zone NOT NULL DEFAULT pg_catalog.now(),
    kpa_fecha_actualizacion timestamp with time zone NOT NULL DEFAULT pg_catalog.now(),
    kpa_usuario_actualizo uuid NOT NULL,
    CONSTRAINT pk_evp_kpa_kiosco_pin_administrativo
        PRIMARY KEY (kpa_cuenta_id, kpa_evento_id),
    CONSTRAINT fk_evp_kpa_evento
        FOREIGN KEY (kpa_cuenta_id, kpa_evento_id)
        REFERENCES public.evp_eve_evento (eve_cuenta_id, eve_evento_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION,
    CONSTRAINT fk_evp_kpa_usuario_actualizo
        FOREIGN KEY (kpa_usuario_actualizo)
        REFERENCES public.evp_usr_usuario (usr_usuario_id)
        ON UPDATE NO ACTION ON DELETE NO ACTION,
    CONSTRAINT ck_evp_kpa_estado
        CHECK (kpa_estado::text = ANY (ARRAY['Activo'::text, 'Inactivo'::text])),
    CONSTRAINT ck_evp_kpa_pin_hash_no_vacio
        CHECK (pg_catalog.length(kpa_pin_hash) > 0)
);

ALTER TABLE public.evp_kpa_kiosco_pin_administrativo ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.evp_kpa_kiosco_pin_administrativo FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.evp_kpa_validar_pin_administrativo(
    p_cuenta_id integer,
    p_evento_id integer,
    p_pin text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
    v_pin_hash text;
BEGIN
    -- Todas las negativas publicas son deliberadamente indistinguibles.
    IF auth.uid() IS NULL OR p_pin IS NULL OR p_pin !~ '^[0-9]{6}$' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    SELECT * INTO v_actor
    FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    SELECT * INTO v_cuenta
    FROM public.evp_cta_cuenta
    WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND OR v_cuenta.cta_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    SELECT * INTO v_evento
    FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND OR v_evento.eve_estado <> 'Activo' OR v_evento.eve_fase_evento <> 'En_proceso' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    IF NOT v_actor.usr_es_usuario_master
       AND NOT EXISTS (
           SELECT 1 FROM public.evp_ucu_usuario_cuenta r
           WHERE r.ucu_usuario_id = v_actor.usr_usuario_id
             AND r.ucu_cuenta_id = p_cuenta_id
             AND r.ucu_estado = 'Activo'
             AND r.ucu_rol = 'Administrador'
       )
       AND NOT EXISTS (
           SELECT 1
           FROM public.evp_ucu_usuario_cuenta r
           JOIN public.evp_uev_usuario_evento e
             ON e.uev_usuario_id = r.ucu_usuario_id
            AND e.uev_cuenta_id = p_cuenta_id
            AND e.uev_evento_id = p_evento_id
           WHERE r.ucu_usuario_id = v_actor.usr_usuario_id
             AND r.ucu_cuenta_id = p_cuenta_id
             AND r.ucu_estado = 'Activo'
             AND r.ucu_rol = 'Operador'
             AND e.uev_estado = 'Activo'
       ) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    SELECT kpa_pin_hash INTO v_pin_hash
    FROM public.evp_kpa_kiosco_pin_administrativo
    WHERE kpa_cuenta_id = p_cuenta_id
      AND kpa_evento_id = p_evento_id
      AND kpa_estado = 'Activo';
    IF NOT FOUND OR extensions.crypt(p_pin, v_pin_hash) <> v_pin_hash THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
    END IF;

    RETURN pg_catalog.jsonb_build_object('ok', true, 'code', 'KIOSK_ADMIN_ALLOWED');
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_DENIED');
END;
$function$;

CREATE OR REPLACE FUNCTION public.evp_kpa_configurar_pin_administrativo(
    p_cuenta_id integer,
    p_evento_id integer,
    p_pin text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    v_actor public.evp_usr_usuario%ROWTYPE;
    v_cuenta public.evp_cta_cuenta%ROWTYPE;
    v_evento public.evp_eve_evento%ROWTYPE;
BEGIN
    IF auth.uid() IS NULL OR p_pin IS NULL OR p_pin !~ '^[0-9]{6}$' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
    END IF;

    SELECT * INTO v_actor
    FROM public.evp_usr_usuario
    WHERE usr_usuario_auth_uuid = auth.uid() AND usr_estado = 'Activo';
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
    END IF;

    SELECT * INTO v_cuenta
    FROM public.evp_cta_cuenta
    WHERE cta_cuenta_id = p_cuenta_id;
    IF NOT FOUND OR v_cuenta.cta_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
    END IF;
    SELECT * INTO v_evento
    FROM public.evp_eve_evento
    WHERE eve_cuenta_id = p_cuenta_id AND eve_evento_id = p_evento_id;
    IF NOT FOUND OR v_evento.eve_estado <> 'Activo' THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
    END IF;

    IF NOT v_actor.usr_es_usuario_master
       AND NOT EXISTS (
           SELECT 1 FROM public.evp_ucu_usuario_cuenta r
           WHERE r.ucu_usuario_id = v_actor.usr_usuario_id
             AND r.ucu_cuenta_id = p_cuenta_id
             AND r.ucu_estado = 'Activo'
             AND r.ucu_rol = 'Administrador'
       ) THEN
        RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
    END IF;

    INSERT INTO public.evp_kpa_kiosco_pin_administrativo (
        kpa_cuenta_id, kpa_evento_id, kpa_pin_hash, kpa_estado,
        kpa_fecha_creacion, kpa_fecha_actualizacion, kpa_usuario_actualizo
    ) VALUES (
        p_cuenta_id, p_evento_id,
        extensions.crypt(p_pin, extensions.gen_salt('bf', 12)), 'Activo',
        pg_catalog.now(), pg_catalog.now(), v_actor.usr_usuario_id
    ) ON CONFLICT (kpa_cuenta_id, kpa_evento_id) DO UPDATE
        SET kpa_pin_hash = EXCLUDED.kpa_pin_hash,
            kpa_estado = 'Activo',
            kpa_fecha_actualizacion = EXCLUDED.kpa_fecha_actualizacion,
            kpa_usuario_actualizo = EXCLUDED.kpa_usuario_actualizo;

    RETURN pg_catalog.jsonb_build_object('ok', true, 'code', 'KIOSK_ADMIN_PIN_CONFIGURED');
EXCEPTION WHEN OTHERS THEN
    RETURN pg_catalog.jsonb_build_object('ok', false, 'code', 'KIOSK_ADMIN_CONFIG_DENIED');
END;
$function$;

ALTER FUNCTION public.evp_kpa_validar_pin_administrativo(integer, integer, text) OWNER TO postgres;
ALTER FUNCTION public.evp_kpa_configurar_pin_administrativo(integer, integer, text) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.evp_kpa_validar_pin_administrativo(integer, integer, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.evp_kpa_configurar_pin_administrativo(integer, integer, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.evp_kpa_validar_pin_administrativo(integer, integer, text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.evp_kpa_configurar_pin_administrativo(integer, integer, text) TO authenticated;
