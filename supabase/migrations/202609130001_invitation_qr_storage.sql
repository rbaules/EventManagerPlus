-- EventPlus QR-1B: almacenamiento de codigos QR de invitaciones.
-- El acceso cliente queda cerrado hasta que existan RPC SECURITY DEFINER.
CREATE TABLE public.evp_iqr_invitacion_qr (
    iqr_invitacion_qr_uuid uuid
        DEFAULT extensions.gen_random_uuid()
        NOT NULL,
    iqr_cuenta_id integer NOT NULL,
    iqr_evento_id integer NOT NULL,
    iqr_invitacion_id integer NOT NULL,
    iqr_codigo character varying(4) NOT NULL,
    iqr_estado character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    iqr_valido_desde timestamp with time zone NOT NULL,
    iqr_valido_hasta timestamp with time zone NOT NULL,
    iqr_fecha_creacion timestamp with time zone DEFAULT now() NOT NULL,
    iqr_fecha_revocacion timestamp with time zone,
    CONSTRAINT pk_evp_iqr_invitacion_qr
        PRIMARY KEY (iqr_invitacion_qr_uuid),
    CONSTRAINT fk_evp_iqr_invitacion_qr_invitacion
        FOREIGN KEY (iqr_cuenta_id, iqr_evento_id, iqr_invitacion_id)
        REFERENCES public.evp_inv_invitacion (
            inv_cuenta_id,
            inv_evento_id,
            inv_invitacion_id
        )
        ON UPDATE NO ACTION
        ON DELETE NO ACTION,
    CONSTRAINT uq_evp_iqr_cuenta_evento_codigo
        UNIQUE (iqr_cuenta_id, iqr_evento_id, iqr_codigo),
    CONSTRAINT ck_evp_iqr_codigo_formato
        CHECK (iqr_codigo::text ~ '^[A-Z0-9]{4}$'::text),
    CONSTRAINT ck_evp_iqr_estado
        CHECK (iqr_estado::text = ANY (ARRAY['Activo'::text, 'Revocado'::text])),
    CONSTRAINT ck_evp_iqr_rango_vigencia
        CHECK (iqr_valido_hasta > iqr_valido_desde),
    CONSTRAINT ck_evp_iqr_revocacion_coherente
        CHECK (
            (iqr_estado::text = 'Activo'::text AND iqr_fecha_revocacion IS NULL)
            OR
            (iqr_estado::text = 'Revocado'::text AND iqr_fecha_revocacion IS NOT NULL)
        )
);

CREATE UNIQUE INDEX ux_evp_iqr_invitacion_activa
    ON public.evp_iqr_invitacion_qr (
        iqr_cuenta_id,
        iqr_evento_id,
        iqr_invitacion_id
    )
    WHERE iqr_estado::text = 'Activo'::text;

ALTER TABLE public.evp_iqr_invitacion_qr ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.evp_iqr_invitacion_qr FROM PUBLIC;
REVOKE ALL ON TABLE public.evp_iqr_invitacion_qr FROM anon;
REVOKE ALL ON TABLE public.evp_iqr_invitacion_qr FROM authenticated;
