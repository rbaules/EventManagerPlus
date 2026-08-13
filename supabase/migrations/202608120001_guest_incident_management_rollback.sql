-- El rollback elimina solo la RPC. No modifica novedades ni datos existentes.
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM anon;
REVOKE ALL ON FUNCTION public.evp_admin_guardar_novedad_invitado(uuid, text) FROM authenticated;
DROP FUNCTION IF EXISTS public.evp_admin_guardar_novedad_invitado(uuid, text);
