-- REGISTRO REPRODUCIBLE: aplicado manualmente en Supabase el 2026-08-02.
-- Es idempotente: repetir SET DEFAULT 'Otro' conserva el mismo estado.
-- No volver a ejecutarlo en el entorno actual; usarlo solo para sincronizar
-- otros entornos que todavia tengan un default distinto.
ALTER TABLE public.evp_eve_evento
ALTER COLUMN eve_tipo_evento
SET DEFAULT 'Otro';
