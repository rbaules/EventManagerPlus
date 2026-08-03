


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE OR REPLACE FUNCTION "public"."evp_es_usuario_master"() RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
    SELECT COALESCE((
        SELECT u.usr_es_usuario_master
        FROM public.evp_usr_usuario u
        WHERE u.usr_usuario_auth_uuid = auth.uid()
          AND u.usr_estado = 'Activo'
        LIMIT 1
    ), false);
$$;


ALTER FUNCTION "public"."evp_es_usuario_master"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_evento_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.eve_evento_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext('evp_eve_evento:' || NEW.eve_cuenta_id::text));

        SELECT COALESCE(MAX(eve_evento_id), 0) + 1
        INTO NEW.eve_evento_id
        FROM public.evp_eve_evento
        WHERE eve_cuenta_id = NEW.eve_cuenta_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_evento_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_invitacion_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.inv_invitacion_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext(
            'evp_inv_invitacion:' || NEW.inv_cuenta_id::text || ':' || NEW.inv_evento_id::text
        ));

        SELECT COALESCE(MAX(inv_invitacion_id), 0) + 1
        INTO NEW.inv_invitacion_id
        FROM public.evp_inv_invitacion
        WHERE inv_cuenta_id = NEW.inv_cuenta_id
          AND inv_evento_id = NEW.inv_evento_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_invitacion_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_invitado_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.ivt_invitado_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext(
            'evp_ivt_invitado:' || NEW.ivt_cuenta_id::text || ':' ||
            NEW.ivt_evento_id::text || ':' || NEW.ivt_invitacion_id::text
        ));

        SELECT COALESCE(MAX(ivt_invitado_id), 0) + 1
        INTO NEW.ivt_invitado_id
        FROM public.evp_ivt_invitado
        WHERE ivt_cuenta_id = NEW.ivt_cuenta_id
          AND ivt_evento_id = NEW.ivt_evento_id
          AND ivt_invitacion_id = NEW.ivt_invitacion_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_invitado_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_lugar_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.lug_lugar_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext('evp_lug_lugar:' || NEW.lug_cuenta_id::text));

        SELECT COALESCE(MAX(lug_lugar_id), 0) + 1
        INTO NEW.lug_lugar_id
        FROM public.evp_lug_lugar
        WHERE lug_cuenta_id = NEW.lug_cuenta_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_lugar_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_mesa_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.mes_mesa_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext(
            'evp_mes_mesa:' || NEW.mes_cuenta_id::text || ':' || NEW.mes_evento_id::text
        ));

        SELECT COALESCE(MAX(mes_mesa_id), 0) + 1
        INTO NEW.mes_mesa_id
        FROM public.evp_mes_mesa
        WHERE mes_cuenta_id = NEW.mes_cuenta_id
          AND mes_evento_id = NEW.mes_evento_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_mesa_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_salon_id"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.sal_salon_id IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtext(
            'evp_sal_salon:' || NEW.sal_cuenta_id::text || ':' || NEW.sal_lugar_id::text
        ));

        SELECT COALESCE(MAX(sal_salon_id), 0) + 1
        INTO NEW.sal_salon_id
        FROM public.evp_sal_salon
        WHERE sal_cuenta_id = NEW.sal_cuenta_id
          AND sal_lugar_id = NEW.sal_lugar_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_salon_id"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_usuario_cuenta_default"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.ucu_estado = 'Activo' THEN
        UPDATE public.evp_usr_usuario
        SET usr_cuenta_id_default = NEW.ucu_cuenta_id
        WHERE usr_usuario_id = NEW.ucu_usuario_id
          AND usr_cuenta_id_default IS NULL;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_usuario_cuenta_default"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_set_usuario_evento_default"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    IF NEW.uev_estado = 'Activo' THEN
        UPDATE public.evp_usr_usuario
        SET
            usr_cuenta_id_default = COALESCE(usr_cuenta_id_default, NEW.uev_cuenta_id),
            usr_evento_id_default = CASE
                WHEN usr_evento_id_default IS NULL
                     AND (usr_cuenta_id_default IS NULL OR usr_cuenta_id_default = NEW.uev_cuenta_id)
                THEN NEW.uev_evento_id
                ELSE usr_evento_id_default
            END
        WHERE usr_usuario_id = NEW.uev_usuario_id;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_set_usuario_evento_default"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_touch_invitado"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.ivt_invitado_mod := now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_touch_invitado"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_touch_usuario"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.usr_modificado := now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_touch_usuario"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_fn_vincular_usuario_auth"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public', 'auth', 'extensions'
    AS $$
DECLARE
    v_nombre text;
BEGIN
    IF NEW.email IS NULL THEN
        RETURN NEW;
    END IF;

    v_nombre := COALESCE(
        NEW.raw_user_meta_data ->> 'full_name',
        NEW.raw_user_meta_data ->> 'name',
        NEW.email
    );

    UPDATE public.evp_usr_usuario
    SET
        usr_usuario_auth_uuid = NEW.id,
        usr_estado = CASE
            WHEN usr_estado = 'Preregistrado' THEN 'Activo'
            ELSE usr_estado
        END,
        usr_modificado = now()
    WHERE lower(trim(usr_email)) = lower(trim(NEW.email))
      AND usr_usuario_auth_uuid IS NULL;

    IF NOT FOUND THEN
        INSERT INTO public.evp_usr_usuario (
            usr_nombre_usuario,
            usr_nombre_usuario_abrev,
            usr_usuario_auth_uuid,
            usr_es_usuario_master,
            usr_email,
            usr_estado
        ) VALUES (
            left(v_nombre, 50),
            left(v_nombre, 12),
            NEW.id,
            false,
            NEW.email,
            'Inactivo'
        );
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."evp_fn_vincular_usuario_auth"() OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_normalizar_texto"("p_texto" "text") RETURNS "text"
    LANGUAGE "sql" IMMUTABLE PARALLEL SAFE
    AS $$
    SELECT regexp_replace(
        lower(trim(extensions.unaccent(coalesce(p_texto, '')))),
        '\s+',
        ' ',
        'g'
    );
$$;


ALTER FUNCTION "public"."evp_normalizar_texto"("p_texto" "text") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_puede_ver_evento"("p_cuenta_id" integer, "p_evento_id" integer) RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
    SELECT public.evp_es_usuario_master()
        OR EXISTS (
            SELECT 1
            FROM public.evp_ucu_usuario_cuenta ucu
            JOIN public.evp_usr_usuario usr
              ON usr.usr_usuario_id = ucu.ucu_usuario_id
            WHERE usr.usr_usuario_auth_uuid = auth.uid()
              AND usr.usr_estado = 'Activo'
              AND ucu.ucu_cuenta_id = p_cuenta_id
              AND ucu.ucu_estado = 'Activo'
              AND ucu.ucu_rol IN ('Administrador', 'Consulta')
        )
        OR EXISTS (
            SELECT 1
            FROM public.evp_uev_usuario_evento uev
            JOIN public.evp_usr_usuario usr
              ON usr.usr_usuario_id = uev.uev_usuario_id
            WHERE usr.usr_usuario_auth_uuid = auth.uid()
              AND usr.usr_estado = 'Activo'
              AND uev.uev_cuenta_id = p_cuenta_id
              AND uev.uev_evento_id = p_evento_id
              AND uev.uev_estado = 'Activo'
        );
$$;


ALTER FUNCTION "public"."evp_puede_ver_evento"("p_cuenta_id" integer, "p_evento_id" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_tiene_acceso_cuenta"("p_cuenta_id" integer) RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
    SELECT public.evp_es_usuario_master()
        OR EXISTS (
            SELECT 1
            FROM public.evp_ucu_usuario_cuenta ucu
            JOIN public.evp_usr_usuario usr
              ON usr.usr_usuario_id = ucu.ucu_usuario_id
            WHERE usr.usr_usuario_auth_uuid = auth.uid()
              AND usr.usr_estado = 'Activo'
              AND ucu.ucu_cuenta_id = p_cuenta_id
              AND ucu.ucu_estado = 'Activo'
        );
$$;


ALTER FUNCTION "public"."evp_tiene_acceso_cuenta"("p_cuenta_id" integer) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."evp_usuario_id_actual"() RETURNS "uuid"
    LANGUAGE "sql" STABLE SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
    SELECT u.usr_usuario_id
    FROM public.evp_usr_usuario u
    WHERE u.usr_usuario_auth_uuid = auth.uid()
      AND u.usr_estado = 'Activo'
    LIMIT 1;
$$;


ALTER FUNCTION "public"."evp_usuario_id_actual"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."evp_cta_cuenta" (
    "cta_cuenta_id" integer NOT NULL,
    "cta_nombre_cuenta" character varying(100) NOT NULL,
    "cta_nombre_cuenta_abrev" character varying(15),
    "cta_nombre_contacto" character varying(80) NOT NULL,
    "cta_telefono_contacto" character varying(20),
    "cta_email_contacto" character varying(254),
    "cta_tipo_suscripcion" character varying(15) DEFAULT 'Demo'::character varying NOT NULL,
    "cta_fecha_venc_suscripcion" "date" NOT NULL,
    "cta_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_cta_estado" CHECK ((("cta_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Inactivo'::character varying, 'Suspendido'::character varying])::"text"[]))),
    CONSTRAINT "chk_cta_tipo_suscripcion" CHECK ((("cta_tipo_suscripcion")::"text" = ANY ((ARRAY['Premium'::character varying, 'Estandar'::character varying, 'Demo'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_cta_cuenta" OWNER TO "postgres";


ALTER TABLE "public"."evp_cta_cuenta" ALTER COLUMN "cta_cuenta_id" ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME "public"."evp_cta_cuenta_cta_cuenta_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



CREATE TABLE IF NOT EXISTS "public"."evp_eve_evento" (
    "eve_cuenta_id" integer NOT NULL,
    "eve_evento_id" integer NOT NULL,
    "eve_nombre_evento" character varying(50) NOT NULL,
    "eve_nombre_evento_abrev" character varying(20),
    "eve_fase_evento" character varying(20) DEFAULT 'Pre_evento'::character varying NOT NULL,
    "eve_tipo_evento" character varying(15) DEFAULT 'Otro'::character varying NOT NULL,
    "eve_lugar_id" integer NOT NULL,
    "eve_salon_id" integer NOT NULL,
    "eve_cant_mesas" integer,
    "eve_fecha_hora_inicio" timestamp with time zone,
    "eve_fecha_hora_fin" timestamp with time zone,
    "eve_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_eve_cant_mesas" CHECK ((("eve_cant_mesas" IS NULL) OR ("eve_cant_mesas" >= 0))),
    CONSTRAINT "chk_eve_estado" CHECK ((("eve_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[]))),
    CONSTRAINT "chk_eve_fase_evento" CHECK ((("eve_fase_evento")::"text" = ANY ((ARRAY['Pre_evento'::character varying, 'En_proceso'::character varying, 'Post_evento'::character varying, 'Cerrado'::character varying])::"text"[]))),
    CONSTRAINT "chk_eve_fechas" CHECK ((("eve_fecha_hora_inicio" IS NULL) OR ("eve_fecha_hora_fin" IS NULL) OR ("eve_fecha_hora_fin" > "eve_fecha_hora_inicio"))),
    CONSTRAINT "chk_eve_tipo_evento" CHECK ((("eve_tipo_evento")::"text" = ANY (ARRAY[('Boda'::character varying)::"text", ('Cumpleaños'::character varying)::"text", ('Quinceaños'::character varying)::"text", ('Corporativo'::character varying)::"text", ('Otro'::character varying)::"text"])))
);


ALTER TABLE "public"."evp_eve_evento" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_inv_invitacion" (
    "inv_cuenta_id" integer NOT NULL,
    "inv_evento_id" integer NOT NULL,
    "inv_invitacion_id" integer NOT NULL,
    "inv_cod_abrev_invitacion" character(3),
    "inv_token_qr_invitacion" character varying(100),
    "inv_destinatario_invitacion" character varying(100) NOT NULL,
    "inv_cant_puestos_reservados" integer DEFAULT 0 NOT NULL,
    "inv_fecha_stdate_enviado" "date",
    "inv_conf_stdate_recibido" boolean DEFAULT false NOT NULL,
    "inv_fecha_invitacion_enviada" "date",
    "inv_conf_invitacion_recibida" boolean DEFAULT false NOT NULL,
    "inv_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_inv_cant_puestos" CHECK (("inv_cant_puestos_reservados" >= 0)),
    CONSTRAINT "chk_inv_estado" CHECK ((("inv_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_inv_invitacion" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_ivt_invitado" (
    "ivt_cuenta_id" integer NOT NULL,
    "ivt_evento_id" integer NOT NULL,
    "ivt_invitacion_id" integer NOT NULL,
    "ivt_invitado_id" integer NOT NULL,
    "ivt_invitado_uuid" "uuid" DEFAULT "extensions"."gen_random_uuid"() NOT NULL,
    "ivt_nombre_invitado" character varying(80) NOT NULL,
    "ivt_nombre_invitado_normalizado" "text" GENERATED ALWAYS AS ("public"."evp_normalizar_texto"(("ivt_nombre_invitado")::"text")) STORED,
    "ivt_es_invitado_principal" boolean DEFAULT false NOT NULL,
    "ivt_es_invitado_imprevisto" boolean DEFAULT false NOT NULL,
    "ivt_email" character varying(254),
    "ivt_telefono" character varying(20),
    "ivt_mesa_id" integer,
    "ivt_puesto_id" integer,
    "ivt_llegada_confirmada" boolean DEFAULT false NOT NULL,
    "ivt_fecha_hora_conf_llegada" timestamp with time zone,
    "ivt_usuario_conf_llegada" "uuid",
    "ivt_tiene_novedad" boolean DEFAULT false NOT NULL,
    "ivt_descripcion_novedad" character varying(200),
    "ivt_novedad_creada" timestamp with time zone,
    "ivt_novedad_creada_por" "uuid",
    "ivt_novedad_mod" timestamp with time zone,
    "ivt_novedad_mod_por" "uuid",
    "ivt_invitado_creado" timestamp with time zone DEFAULT "now"() NOT NULL,
    "ivt_invitado_creado_por" "uuid",
    "ivt_invitado_mod" timestamp with time zone,
    "ivt_invitado_mod_por" "uuid",
    "ivt_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_ivt_estado" CHECK ((("ivt_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[]))),
    CONSTRAINT "chk_ivt_llegada" CHECK ((("ivt_llegada_confirmada" = false) OR (("ivt_llegada_confirmada" = true) AND ("ivt_fecha_hora_conf_llegada" IS NOT NULL)))),
    CONSTRAINT "chk_ivt_puesto" CHECK ((("ivt_puesto_id" IS NULL) OR ("ivt_puesto_id" > 0)))
);


ALTER TABLE "public"."evp_ivt_invitado" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_lug_lugar" (
    "lug_cuenta_id" integer NOT NULL,
    "lug_lugar_id" integer NOT NULL,
    "lug_nombre_lugar" character varying(50) NOT NULL,
    "lug_direccion" character varying(150),
    "lug_ciudad" character varying(50),
    "lug_pais_id" character varying(2),
    "lug_tipo_lugar" character varying(20) DEFAULT 'Otro'::character varying NOT NULL,
    "lug_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_lug_estado" CHECK ((("lug_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[]))),
    CONSTRAINT "chk_lug_tipo_lugar" CHECK ((("lug_tipo_lugar")::"text" = ANY ((ARRAY['Hotel'::character varying, 'Sala de eventos'::character varying, 'Otro'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_lug_lugar" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_mes_mesa" (
    "mes_cuenta_id" integer NOT NULL,
    "mes_evento_id" integer NOT NULL,
    "mes_mesa_id" integer NOT NULL,
    "mes_nombre_mesa" character varying(30) NOT NULL,
    "mes_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_mes_estado" CHECK ((("mes_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_mes_mesa" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_pai_pais" (
    "pai_pais_id" character varying(2) NOT NULL,
    "pai_nombre_pais" character varying(50) NOT NULL
);


ALTER TABLE "public"."evp_pai_pais" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_sal_salon" (
    "sal_cuenta_id" integer NOT NULL,
    "sal_lugar_id" integer NOT NULL,
    "sal_salon_id" integer NOT NULL,
    "sal_nombre_salon" character varying(60) NOT NULL,
    "sal_ubicacion" character varying(100),
    "sal_cant_max_mesas" integer,
    "sal_cant_max_invitados" integer,
    "sal_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_sal_capacidades" CHECK (((("sal_cant_max_mesas" IS NULL) OR ("sal_cant_max_mesas" >= 0)) AND (("sal_cant_max_invitados" IS NULL) OR ("sal_cant_max_invitados" >= 0)))),
    CONSTRAINT "chk_sal_estado" CHECK ((("sal_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_sal_salon" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_ucu_usuario_cuenta" (
    "ucu_cuenta_id" integer NOT NULL,
    "ucu_usuario_id" "uuid" NOT NULL,
    "ucu_rol" character varying(20) NOT NULL,
    "ucu_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_ucu_estado" CHECK ((("ucu_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[]))),
    CONSTRAINT "chk_ucu_rol" CHECK ((("ucu_rol")::"text" = ANY ((ARRAY['Administrador'::character varying, 'Operador'::character varying, 'Consulta'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_ucu_usuario_cuenta" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_uev_usuario_evento" (
    "uev_cuenta_id" integer NOT NULL,
    "uev_evento_id" integer NOT NULL,
    "uev_usuario_id" "uuid" NOT NULL,
    "uev_estado" character varying(15) DEFAULT 'Activo'::character varying NOT NULL,
    CONSTRAINT "chk_uev_estado" CHECK ((("uev_estado")::"text" = ANY ((ARRAY['Activo'::character varying, 'Suspendido'::character varying, 'Inactivo'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_uev_usuario_evento" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."evp_usr_usuario" (
    "usr_usuario_id" "uuid" DEFAULT "extensions"."gen_random_uuid"() NOT NULL,
    "usr_nombre_usuario" character varying(50) NOT NULL,
    "usr_nombre_usuario_abrev" character varying(12) NOT NULL,
    "usr_usuario_auth_uuid" "uuid",
    "usr_es_usuario_master" boolean DEFAULT false NOT NULL,
    "usr_email" character varying(254) NOT NULL,
    "usr_cuenta_id_default" integer,
    "usr_evento_id_default" integer,
    "usr_telefono" character varying(20),
    "usr_creado" timestamp with time zone DEFAULT "now"() NOT NULL,
    "usr_modificado" timestamp with time zone,
    "usr_estado" character varying(15) DEFAULT 'Preregistrado'::character varying NOT NULL,
    CONSTRAINT "chk_usr_default_evento_requiere_cuenta" CHECK ((("usr_evento_id_default" IS NULL) OR ("usr_cuenta_id_default" IS NOT NULL))),
    CONSTRAINT "chk_usr_estado" CHECK ((("usr_estado")::"text" = ANY ((ARRAY['Preregistrado'::character varying, 'Activo'::character varying, 'Inactivo'::character varying, 'Suspendido'::character varying])::"text"[])))
);


ALTER TABLE "public"."evp_usr_usuario" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."evp_vw_evento_resumen" AS
 SELECT "e"."eve_cuenta_id",
    "e"."eve_evento_id",
    "e"."eve_nombre_evento",
    "e"."eve_fase_evento",
    "e"."eve_fecha_hora_inicio",
    "e"."eve_fecha_hora_fin",
    COALESCE("inv"."total_puestos_reservados", (0)::bigint) AS "total_puestos_reservados",
    COALESCE("ivt"."total_invitados_registrados", (0)::bigint) AS "total_invitados_registrados",
    COALESCE("ivt"."total_llegadas_confirmadas", (0)::bigint) AS "total_llegadas_confirmadas",
    COALESCE("ivt"."total_pendientes_llegada", (0)::bigint) AS "total_pendientes_llegada",
    COALESCE("ivt"."total_invitados_imprevistos", (0)::bigint) AS "total_invitados_imprevistos"
   FROM (("public"."evp_eve_evento" "e"
     LEFT JOIN ( SELECT "evp_inv_invitacion"."inv_cuenta_id",
            "evp_inv_invitacion"."inv_evento_id",
            "sum"("evp_inv_invitacion"."inv_cant_puestos_reservados") AS "total_puestos_reservados"
           FROM "public"."evp_inv_invitacion"
          WHERE (("evp_inv_invitacion"."inv_estado")::"text" = 'Activo'::"text")
          GROUP BY "evp_inv_invitacion"."inv_cuenta_id", "evp_inv_invitacion"."inv_evento_id") "inv" ON ((("inv"."inv_cuenta_id" = "e"."eve_cuenta_id") AND ("inv"."inv_evento_id" = "e"."eve_evento_id"))))
     LEFT JOIN ( SELECT "evp_ivt_invitado"."ivt_cuenta_id",
            "evp_ivt_invitado"."ivt_evento_id",
            "count"(*) FILTER (WHERE (("evp_ivt_invitado"."ivt_estado")::"text" = 'Activo'::"text")) AS "total_invitados_registrados",
            "count"(*) FILTER (WHERE ((("evp_ivt_invitado"."ivt_estado")::"text" = 'Activo'::"text") AND ("evp_ivt_invitado"."ivt_llegada_confirmada" = true))) AS "total_llegadas_confirmadas",
            "count"(*) FILTER (WHERE ((("evp_ivt_invitado"."ivt_estado")::"text" = 'Activo'::"text") AND ("evp_ivt_invitado"."ivt_llegada_confirmada" = false))) AS "total_pendientes_llegada",
            "count"(*) FILTER (WHERE ((("evp_ivt_invitado"."ivt_estado")::"text" = 'Activo'::"text") AND ("evp_ivt_invitado"."ivt_es_invitado_imprevisto" = true))) AS "total_invitados_imprevistos"
           FROM "public"."evp_ivt_invitado"
          GROUP BY "evp_ivt_invitado"."ivt_cuenta_id", "evp_ivt_invitado"."ivt_evento_id") "ivt" ON ((("ivt"."ivt_cuenta_id" = "e"."eve_cuenta_id") AND ("ivt"."ivt_evento_id" = "e"."eve_evento_id"))));


ALTER VIEW "public"."evp_vw_evento_resumen" OWNER TO "postgres";


CREATE OR REPLACE VIEW "public"."evp_vw_mesa_resumen" AS
 SELECT "m"."mes_cuenta_id",
    "m"."mes_evento_id",
    "m"."mes_mesa_id",
    "m"."mes_nombre_mesa",
    "count"("i"."ivt_invitado_id") FILTER (WHERE (("i"."ivt_estado")::"text" = 'Activo'::"text")) AS "cant_puestos_reservados",
    "count"("i"."ivt_invitado_id") FILTER (WHERE ((("i"."ivt_estado")::"text" = 'Activo'::"text") AND ("i"."ivt_llegada_confirmada" = true))) AS "cant_puestos_confirmados",
    "count"("i"."ivt_invitado_id") FILTER (WHERE ((("i"."ivt_estado")::"text" = 'Activo'::"text") AND ("i"."ivt_llegada_confirmada" = false))) AS "cant_puestos_pendientes"
   FROM ("public"."evp_mes_mesa" "m"
     LEFT JOIN "public"."evp_ivt_invitado" "i" ON ((("i"."ivt_cuenta_id" = "m"."mes_cuenta_id") AND ("i"."ivt_evento_id" = "m"."mes_evento_id") AND ("i"."ivt_mesa_id" = "m"."mes_mesa_id"))))
  GROUP BY "m"."mes_cuenta_id", "m"."mes_evento_id", "m"."mes_mesa_id", "m"."mes_nombre_mesa";


ALTER VIEW "public"."evp_vw_mesa_resumen" OWNER TO "postgres";


ALTER TABLE ONLY "public"."evp_cta_cuenta"
    ADD CONSTRAINT "evp_cta_cuenta_pkey" PRIMARY KEY ("cta_cuenta_id");



ALTER TABLE ONLY "public"."evp_eve_evento"
    ADD CONSTRAINT "evp_eve_evento_pkey" PRIMARY KEY ("eve_cuenta_id", "eve_evento_id");



ALTER TABLE ONLY "public"."evp_inv_invitacion"
    ADD CONSTRAINT "evp_inv_invitacion_inv_token_qr_invitacion_key" UNIQUE ("inv_token_qr_invitacion");



ALTER TABLE ONLY "public"."evp_inv_invitacion"
    ADD CONSTRAINT "evp_inv_invitacion_pkey" PRIMARY KEY ("inv_cuenta_id", "inv_evento_id", "inv_invitacion_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "evp_ivt_invitado_pkey" PRIMARY KEY ("ivt_cuenta_id", "ivt_evento_id", "ivt_invitacion_id", "ivt_invitado_id");



ALTER TABLE ONLY "public"."evp_lug_lugar"
    ADD CONSTRAINT "evp_lug_lugar_pkey" PRIMARY KEY ("lug_cuenta_id", "lug_lugar_id");



ALTER TABLE ONLY "public"."evp_mes_mesa"
    ADD CONSTRAINT "evp_mes_mesa_pkey" PRIMARY KEY ("mes_cuenta_id", "mes_evento_id", "mes_mesa_id");



ALTER TABLE ONLY "public"."evp_pai_pais"
    ADD CONSTRAINT "evp_pai_pais_pkey" PRIMARY KEY ("pai_pais_id");



ALTER TABLE ONLY "public"."evp_sal_salon"
    ADD CONSTRAINT "evp_sal_salon_pkey" PRIMARY KEY ("sal_cuenta_id", "sal_lugar_id", "sal_salon_id");



ALTER TABLE ONLY "public"."evp_ucu_usuario_cuenta"
    ADD CONSTRAINT "evp_ucu_usuario_cuenta_pkey" PRIMARY KEY ("ucu_cuenta_id", "ucu_usuario_id");



ALTER TABLE ONLY "public"."evp_uev_usuario_evento"
    ADD CONSTRAINT "evp_uev_usuario_evento_pkey" PRIMARY KEY ("uev_cuenta_id", "uev_evento_id", "uev_usuario_id");



ALTER TABLE ONLY "public"."evp_usr_usuario"
    ADD CONSTRAINT "evp_usr_usuario_pkey" PRIMARY KEY ("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_usr_usuario"
    ADD CONSTRAINT "evp_usr_usuario_usr_usuario_auth_uuid_key" UNIQUE ("usr_usuario_auth_uuid");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "uq_ivt_invitado_uuid" UNIQUE ("ivt_invitado_uuid");



CREATE UNIQUE INDEX "ux_evp_inv_cod_abrev_evento" ON "public"."evp_inv_invitacion" USING "btree" ("inv_cuenta_id", "inv_evento_id", "inv_cod_abrev_invitacion") WHERE (("inv_cod_abrev_invitacion" IS NOT NULL) AND (("inv_estado")::"text" <> 'Inactivo'::"text"));



CREATE UNIQUE INDEX "ux_evp_ivt_nombre_evento_activo" ON "public"."evp_ivt_invitado" USING "btree" ("ivt_cuenta_id", "ivt_evento_id", "ivt_nombre_invitado_normalizado") WHERE (("ivt_estado")::"text" <> 'Inactivo'::"text");



CREATE UNIQUE INDEX "ux_evp_ivt_principal_invitacion" ON "public"."evp_ivt_invitado" USING "btree" ("ivt_cuenta_id", "ivt_evento_id", "ivt_invitacion_id") WHERE (("ivt_es_invitado_principal" = true) AND (("ivt_estado")::"text" <> 'Inactivo'::"text"));



CREATE UNIQUE INDEX "ux_evp_usr_email_norm" ON "public"."evp_usr_usuario" USING "btree" ("lower"(TRIM(BOTH FROM "usr_email")));



CREATE OR REPLACE TRIGGER "trg_evp_eve_set_id" BEFORE INSERT ON "public"."evp_eve_evento" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_evento_id"();



CREATE OR REPLACE TRIGGER "trg_evp_inv_set_id" BEFORE INSERT ON "public"."evp_inv_invitacion" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_invitacion_id"();



CREATE OR REPLACE TRIGGER "trg_evp_ivt_set_id" BEFORE INSERT ON "public"."evp_ivt_invitado" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_invitado_id"();



CREATE OR REPLACE TRIGGER "trg_evp_ivt_touch" BEFORE UPDATE ON "public"."evp_ivt_invitado" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_touch_invitado"();



CREATE OR REPLACE TRIGGER "trg_evp_lug_set_id" BEFORE INSERT ON "public"."evp_lug_lugar" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_lugar_id"();



CREATE OR REPLACE TRIGGER "trg_evp_mes_set_id" BEFORE INSERT ON "public"."evp_mes_mesa" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_mesa_id"();



CREATE OR REPLACE TRIGGER "trg_evp_sal_set_id" BEFORE INSERT ON "public"."evp_sal_salon" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_salon_id"();



CREATE OR REPLACE TRIGGER "trg_evp_ucu_set_default" AFTER INSERT ON "public"."evp_ucu_usuario_cuenta" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_usuario_cuenta_default"();



CREATE OR REPLACE TRIGGER "trg_evp_uev_set_default" AFTER INSERT ON "public"."evp_uev_usuario_evento" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_set_usuario_evento_default"();



CREATE OR REPLACE TRIGGER "trg_evp_usr_touch" BEFORE UPDATE ON "public"."evp_usr_usuario" FOR EACH ROW EXECUTE FUNCTION "public"."evp_fn_touch_usuario"();



ALTER TABLE ONLY "public"."evp_usr_usuario"
    ADD CONSTRAINT "evp_usr_usuario_usr_cuenta_id_default_fkey" FOREIGN KEY ("usr_cuenta_id_default") REFERENCES "public"."evp_cta_cuenta"("cta_cuenta_id");



ALTER TABLE ONLY "public"."evp_usr_usuario"
    ADD CONSTRAINT "evp_usr_usuario_usr_usuario_auth_uuid_fkey" FOREIGN KEY ("usr_usuario_auth_uuid") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."evp_eve_evento"
    ADD CONSTRAINT "fk_eve_salon" FOREIGN KEY ("eve_cuenta_id", "eve_lugar_id", "eve_salon_id") REFERENCES "public"."evp_sal_salon"("sal_cuenta_id", "sal_lugar_id", "sal_salon_id");



ALTER TABLE ONLY "public"."evp_inv_invitacion"
    ADD CONSTRAINT "fk_inv_evento" FOREIGN KEY ("inv_cuenta_id", "inv_evento_id") REFERENCES "public"."evp_eve_evento"("eve_cuenta_id", "eve_evento_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_invitacion" FOREIGN KEY ("ivt_cuenta_id", "ivt_evento_id", "ivt_invitacion_id") REFERENCES "public"."evp_inv_invitacion"("inv_cuenta_id", "inv_evento_id", "inv_invitacion_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_invitado_creado_por" FOREIGN KEY ("ivt_invitado_creado_por") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_invitado_mod_por" FOREIGN KEY ("ivt_invitado_mod_por") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_mesa" FOREIGN KEY ("ivt_cuenta_id", "ivt_evento_id", "ivt_mesa_id") REFERENCES "public"."evp_mes_mesa"("mes_cuenta_id", "mes_evento_id", "mes_mesa_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_novedad_creada_por" FOREIGN KEY ("ivt_novedad_creada_por") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_novedad_mod_por" FOREIGN KEY ("ivt_novedad_mod_por") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_ivt_invitado"
    ADD CONSTRAINT "fk_ivt_usuario_conf_llegada" FOREIGN KEY ("ivt_usuario_conf_llegada") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_lug_lugar"
    ADD CONSTRAINT "fk_lug_cuenta" FOREIGN KEY ("lug_cuenta_id") REFERENCES "public"."evp_cta_cuenta"("cta_cuenta_id");



ALTER TABLE ONLY "public"."evp_lug_lugar"
    ADD CONSTRAINT "fk_lug_pais" FOREIGN KEY ("lug_pais_id") REFERENCES "public"."evp_pai_pais"("pai_pais_id");



ALTER TABLE ONLY "public"."evp_mes_mesa"
    ADD CONSTRAINT "fk_mes_evento" FOREIGN KEY ("mes_cuenta_id", "mes_evento_id") REFERENCES "public"."evp_eve_evento"("eve_cuenta_id", "eve_evento_id");



ALTER TABLE ONLY "public"."evp_sal_salon"
    ADD CONSTRAINT "fk_sal_lugar" FOREIGN KEY ("sal_cuenta_id", "sal_lugar_id") REFERENCES "public"."evp_lug_lugar"("lug_cuenta_id", "lug_lugar_id");



ALTER TABLE ONLY "public"."evp_ucu_usuario_cuenta"
    ADD CONSTRAINT "fk_ucu_cuenta" FOREIGN KEY ("ucu_cuenta_id") REFERENCES "public"."evp_cta_cuenta"("cta_cuenta_id");



ALTER TABLE ONLY "public"."evp_ucu_usuario_cuenta"
    ADD CONSTRAINT "fk_ucu_usuario" FOREIGN KEY ("ucu_usuario_id") REFERENCES "public"."evp_usr_usuario"("usr_usuario_id");



ALTER TABLE ONLY "public"."evp_uev_usuario_evento"
    ADD CONSTRAINT "fk_uev_evento" FOREIGN KEY ("uev_cuenta_id", "uev_evento_id") REFERENCES "public"."evp_eve_evento"("eve_cuenta_id", "eve_evento_id");



ALTER TABLE ONLY "public"."evp_uev_usuario_evento"
    ADD CONSTRAINT "fk_uev_usuario_cuenta" FOREIGN KEY ("uev_cuenta_id", "uev_usuario_id") REFERENCES "public"."evp_ucu_usuario_cuenta"("ucu_cuenta_id", "ucu_usuario_id");



ALTER TABLE ONLY "public"."evp_usr_usuario"
    ADD CONSTRAINT "fk_usr_evento_default" FOREIGN KEY ("usr_cuenta_id_default", "usr_evento_id_default") REFERENCES "public"."evp_eve_evento"("eve_cuenta_id", "eve_evento_id");



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_es_usuario_master"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_es_usuario_master"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_es_usuario_master"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_evento_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_evento_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_evento_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_invitacion_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_invitacion_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_invitacion_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_invitado_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_invitado_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_invitado_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_lugar_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_lugar_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_lugar_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_mesa_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_mesa_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_mesa_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_salon_id"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_salon_id"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_salon_id"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_cuenta_default"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_cuenta_default"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_cuenta_default"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_evento_default"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_evento_default"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_set_usuario_evento_default"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_touch_invitado"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_touch_invitado"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_touch_invitado"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_touch_usuario"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_touch_usuario"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_touch_usuario"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_fn_vincular_usuario_auth"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_fn_vincular_usuario_auth"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_fn_vincular_usuario_auth"() TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_normalizar_texto"("p_texto" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."evp_normalizar_texto"("p_texto" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_normalizar_texto"("p_texto" "text") TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_puede_ver_evento"("p_cuenta_id" integer, "p_evento_id" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."evp_puede_ver_evento"("p_cuenta_id" integer, "p_evento_id" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_puede_ver_evento"("p_cuenta_id" integer, "p_evento_id" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_tiene_acceso_cuenta"("p_cuenta_id" integer) TO "anon";
GRANT ALL ON FUNCTION "public"."evp_tiene_acceso_cuenta"("p_cuenta_id" integer) TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_tiene_acceso_cuenta"("p_cuenta_id" integer) TO "service_role";



GRANT ALL ON FUNCTION "public"."evp_usuario_id_actual"() TO "anon";
GRANT ALL ON FUNCTION "public"."evp_usuario_id_actual"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."evp_usuario_id_actual"() TO "service_role";



GRANT ALL ON TABLE "public"."evp_cta_cuenta" TO "anon";
GRANT ALL ON TABLE "public"."evp_cta_cuenta" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_cta_cuenta" TO "service_role";



GRANT ALL ON SEQUENCE "public"."evp_cta_cuenta_cta_cuenta_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."evp_cta_cuenta_cta_cuenta_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."evp_cta_cuenta_cta_cuenta_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."evp_eve_evento" TO "anon";
GRANT ALL ON TABLE "public"."evp_eve_evento" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_eve_evento" TO "service_role";



GRANT ALL ON TABLE "public"."evp_inv_invitacion" TO "anon";
GRANT ALL ON TABLE "public"."evp_inv_invitacion" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_inv_invitacion" TO "service_role";



GRANT ALL ON TABLE "public"."evp_ivt_invitado" TO "anon";
GRANT ALL ON TABLE "public"."evp_ivt_invitado" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_ivt_invitado" TO "service_role";



GRANT ALL ON TABLE "public"."evp_lug_lugar" TO "anon";
GRANT ALL ON TABLE "public"."evp_lug_lugar" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_lug_lugar" TO "service_role";



GRANT ALL ON TABLE "public"."evp_mes_mesa" TO "anon";
GRANT ALL ON TABLE "public"."evp_mes_mesa" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_mes_mesa" TO "service_role";



GRANT ALL ON TABLE "public"."evp_pai_pais" TO "anon";
GRANT ALL ON TABLE "public"."evp_pai_pais" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_pai_pais" TO "service_role";



GRANT ALL ON TABLE "public"."evp_sal_salon" TO "anon";
GRANT ALL ON TABLE "public"."evp_sal_salon" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_sal_salon" TO "service_role";



GRANT ALL ON TABLE "public"."evp_ucu_usuario_cuenta" TO "anon";
GRANT ALL ON TABLE "public"."evp_ucu_usuario_cuenta" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_ucu_usuario_cuenta" TO "service_role";



GRANT ALL ON TABLE "public"."evp_uev_usuario_evento" TO "anon";
GRANT ALL ON TABLE "public"."evp_uev_usuario_evento" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_uev_usuario_evento" TO "service_role";



GRANT ALL ON TABLE "public"."evp_usr_usuario" TO "anon";
GRANT ALL ON TABLE "public"."evp_usr_usuario" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_usr_usuario" TO "service_role";



GRANT ALL ON TABLE "public"."evp_vw_evento_resumen" TO "anon";
GRANT ALL ON TABLE "public"."evp_vw_evento_resumen" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_vw_evento_resumen" TO "service_role";



GRANT ALL ON TABLE "public"."evp_vw_mesa_resumen" TO "anon";
GRANT ALL ON TABLE "public"."evp_vw_mesa_resumen" TO "authenticated";
GRANT ALL ON TABLE "public"."evp_vw_mesa_resumen" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";






