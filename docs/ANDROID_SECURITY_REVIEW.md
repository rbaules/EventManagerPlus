# Android Security Review

## Clave usada por el cliente

El cliente usa `SUPABASE_PUBLISHABLE_KEY` mediante `db.py`.

No se usa `service_role` en el cliente.

## Configuracion empaquetada

Para Android se empaqueta solo configuracion publica en `app_public_config.py`:

- URL publica de Supabase.
- Publishable key publica.

No debe empaquetarse `.env` completo.

## Archivos excluidos

`.gitignore` excluye:

- `.env`
- `env/`
- `.venv/`
- `build/`
- `dist/`
- `*.apk`
- `*.aab`
- `*.jks`
- `*.keystore`
- `app_public_config.py`

## RLS

No se desactivo RLS desde el repositorio. La seguridad efectiva debe verificarse en Supabase para:

- Usuarios.
- Cuentas.
- Eventos.
- Invitados.
- Invitaciones.
- Confirmacion de llegada.
- Reversion de llegada.

## Riesgos pendientes antes de distribucion externa

- Confirmar politicas RLS reales en Supabase con usuarios Master, Administrador y Operador.
- Confirmar que no existe ninguna policy que permita escritura administrativa desde Check-in.
- Confirmar que `eventplusbeta://auth-callback` esta registrado solo para esta app beta.

## Bloqueos

No distribuir fuera del equipo interno hasta validar RLS y OAuth Android en Supabase/Google.
