-- Revierte exclusivamente las RPC creadas por 202609270003.
DROP FUNCTION IF EXISTS public.evp_oper_confirmar_llegadas_invitacion(integer,integer,integer,integer[]);
DROP FUNCTION IF EXISTS public.evp_oper_obtener_grupo_invitacion(integer,integer,integer);
