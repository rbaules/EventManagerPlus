-- ROLLBACK SEGURO / OPERACION DE RECUPERACION.
-- El default anterior ('O') viola chk_eve_tipo_evento y no debe restaurarse.
-- El cambio no tiene una reversion compatible distinta; esta operacion
-- idempotente mantiene 'Otro' para asegurar que el esquema siga siendo valido.
ALTER TABLE public.evp_eve_evento
ALTER COLUMN eve_tipo_evento
SET DEFAULT 'Otro';
