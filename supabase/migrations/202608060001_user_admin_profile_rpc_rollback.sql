drop function if exists public.evp_admin_cambiar_master(uuid,boolean);
drop function if exists public.evp_admin_cambiar_estado_usuario(uuid,text);
drop function if exists public.evp_admin_actualizar_usuario(uuid,text,text);
drop function if exists public.evp_admin_crear_usuario(text,text,boolean,integer,text);
drop function if exists public.evp_admin_crear_usuario(text,text,boolean);
drop function if exists public.evp_admin_actor_puede_preregistrar();
drop function if exists public.evp_admin_actor_es_master();
