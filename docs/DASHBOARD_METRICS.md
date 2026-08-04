# Dashboard operativo

El dashboard consulta únicamente el evento activo y usa dos lecturas: invitados
activos de `evp_ivt_invitado` y mesas activas de `evp_mes_mesa`.

## Fuentes y reglas

- Invitados: `ivt_estado = 'Activo'`.
- Llegadas: `ivt_llegada_confirmada` y su timestamp real
  `ivt_fecha_hora_conf_llegada`.
- Novedades: invitados únicos por `ivt_invitado_uuid` con
  `ivt_tiene_novedad = true`.
- Mesas: `mes_estado = 'Activo'`; la asignación se obtiene de `ivt_mesa_id`.
- Inicio programado: `eve_fecha_hora_inicio` del evento activo.
- Una mesa vacía no participa como completa, parcial ni sin llegadas.
- Mesa parcial requiere al menos dos invitados, alguna llegada y algún pendiente.

Los porcentajes de mesas usan únicamente mesas con invitados activos asignados.
Los porcentajes con denominador cero son `0 %`.

## Zona horaria y afluencia

Los campos son `timestamptz`. Las horas se presentan con el offset incluido en
`eve_fecha_hora_inicio`, que es el criterio ya usado por EventPlus al conservar
los offsets ISO 8601 enviados a Supabase. Si no hay inicio válido, las horas de
llegada conservan el offset devuelto por Supabase y el gráfico no se genera.

La afluencia contiene exactamente ocho intervalos consecutivos de 15 minutos a
partir de `eve_fecha_hora_inicio`. Una llegada en un límite exacto pertenece al
intervalo que comienza en ese límite. Las llegadas anticipadas se acumulan en el
primer intervalo; las ocurridas exactamente a las dos horas o después se excluyen.
La aritmética usa timestamps con zona y funciona al atravesar medianoche.

## Actualización

El dashboard se recarga al entrar, al cambiar de evento y después de operaciones
que invalidan invitados o llegadas. Mientras está visible se actualiza cada 30
segundos. El controlador pertenece a una sola `Page`, impide tareas duplicadas y
se cancela al salir, desconectarse o cerrar sesión.
