-- Revierte solamente los objetos introducidos por 202608100001.
-- Tras aplicarlo, volver a aplicar 202608080001_user_admin_profile_8c_fix.sql
-- para reinstalar exactamente las definiciones previas de crear/editar usuario.
drop function if exists public.evp_usuario_actualizar_preferencias(integer,integer);
drop function if exists public.evp_admin_cambiar_estado_cuenta(uuid,integer,text);
drop function if exists public.evp_admin_cambiar_rol_cuenta(uuid,integer,text);
drop function if exists public.evp_admin_crear_usuario(text,text,text,integer,integer);
drop function if exists public.evp_priv_limpiar_defaults(uuid);
drop function if exists public.evp_priv_usuario_puede_tener_default(uuid,integer,integer);
drop function if exists public.evp_priv_usuario_tiene_acceso(uuid,integer,integer);

-- Estas dos definiciones fueron reemplazadas por la migracion incremental.
-- El runner de rollback debe ejecutar inmediatamente despues el artefacto 8C-Fix
-- indicado arriba; no se altera ni se duplica esa migracion aplicada.
drop function if exists public.evp_admin_actualizar_usuario(uuid,text,text);
