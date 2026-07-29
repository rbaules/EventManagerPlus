-- ROLLBACK PROPUESTO, NO EJECUTADO.
-- Retira solamente el CHECK creado por la propuesta. Un CHECK previo debe
-- restaurarse literalmente desde el inventario guardado antes de aplicarla.

begin;

alter table public.evp_ucu_usuario_cuenta
  drop constraint if exists evp_ucu_usuario_cuenta_ucu_rol_check;

commit;
