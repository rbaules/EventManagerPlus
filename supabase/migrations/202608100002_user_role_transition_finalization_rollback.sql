-- Revierte solamente 202608100002. Restaura las firmas accesibles de 202608100001/202608060001.
drop function if exists public.evp_admin_cambiar_rol_cuenta(uuid,integer,text,integer);
drop function if exists public.evp_admin_retirar_master(uuid,integer,text,integer);
drop function if exists public.evp_admin_convertir_master(uuid);
grant execute on function public.evp_admin_cambiar_master(uuid,boolean) to authenticated;
grant execute on function public.evp_admin_cambiar_rol_cuenta(uuid,integer,text) to authenticated;
