# Métricas del Dashboard

La especificación completa se encuentra en `docs/DASHBOARD_MODULE.md`.

El Dashboard usa únicamente datos del evento autorizado activo. Ejecuta dos
lecturas filtradas por cuenta, evento y estado: invitados activos de
`evp_ivt_invitado` y mesas activas de `evp_mes_mesa`. No hay consultas por fila,
escrituras, SQL remoto ni datos ficticios.

- Llegada: `ivt_llegada_confirmada`; hora: `ivt_fecha_hora_conf_llegada`.
- Novedad: `ivt_tiene_novedad = true` en invitados activos únicos.
- Mesa completa: mesa activa con al menos un invitado activo y todos llegados.
- Porcentaje de mesas: mesas completas / total de mesas activas.
- Afluencia: ocho intervalos `[inicio, final)` de 15 minutos desde
  `eve_fecha_hora_inicio`; se excluyen llegadas anteriores al inicio y las de
  dos horas o más tarde.
- Zona horaria: se conserva el offset ISO 8601 del inicio del evento.

Los denominadores cero producen 0%, acompañado por un estado “Sin invitados”
o “Sin mesas” para evitar interpretaciones engañosas.
