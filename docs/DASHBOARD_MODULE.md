# Módulo Dashboard de EventPlus

## Objetivo y diseño

El Dashboard administrativo presenta un resumen operativo moderno y responsive
del evento activo. La interfaz anterior agrupaba invitados y mesas en tarjetas
grandes, mostraba novedades y horarios, y representaba la afluencia con barras
horizontales. Los datos eran reales, pero no existían KPI individuales ni una
visualización llegados/pendientes.

El rediseño usa ocho tarjetas KPI, dos visualizaciones principales y una barra
de progreso de mesas. En escritorio los KPI ocupan cuatro columnas; en tableta,
dos; en móvil, una. Las visualizaciones se apilan en móvil y no fijan anchos que
provoquen desplazamiento horizontal. Las tarjetas no usan `expand=True` ni
alturas fijas.

## Métricas y fuentes reales

| Métrica | Fuente y criterio |
|---|---|
| Total invitados | `evp_ivt_invitado`, `ivt_estado = 'Activo'`, deduplicado por `ivt_invitado_uuid` |
| Llegaron | `ivt_llegada_confirmada = true` |
| Pendientes | total activos menos llegados |
| Novedades | `ivt_tiene_novedad = true` en invitados activos únicos |
| Total mesas | `evp_mes_mesa`, `mes_estado = 'Activo'` |
| Mesas completas | mesa activa con uno o más invitados activos y todos con llegada confirmada |
| Primera/última llegada | mínimo/máximo de `ivt_fecha_hora_conf_llegada` entre llegados |

Una mesa activa vacía no es completa. El porcentaje de mesas completas usa como
denominador todas las mesas activas; si no hay mesas es 0%. Las vistas
`evp_vw_evento_resumen` y `evp_vw_mesa_resumen` fueron auditadas, pero no se
usan porque no incluyen novedades ni timestamps individuales y la vista de
mesas no expone `mes_estado`. La lectura directa permite resolver todo con dos
consultas totales y evita N+1.

## Intervalos y zona horaria

La afluencia genera exactamente ocho intervalos consecutivos de 15 minutos a
partir de `eve_fecha_hora_inicio`. Cada intervalo es semiabierto `[inicio,
final)`: una llegada en el límite pertenece al siguiente intervalo. Se muestran
ceros; se excluyen registros anteriores al inicio y a partir de las dos horas.
Los timestamps se convierten al offset del inicio del evento antes de comparar.
Sin inicio válido se muestra un estado vacío; sin llegadas se conserva la escala
de ocho intervalos y se informa que aún no hay registros.

## Componentes, paleta y Flet

`views/dashboard_view.py` aporta `dashboard_kpi_card`, `arrivals_chart`,
`attendance_distribution_chart`, `dashboard_progress_card` y
`dashboard_empty_state`. Ninguno consulta datos. `DASHBOARD_COLORS` centraliza
índigo (`#4F46E5`), verde (`#15803D`), ámbar (`#B45309`), rojo suave
(`#B42318`) y grises neutros, con fondos tenues y texto explícito.

Flet 0.85.3 instalado no expone `BarChart` ni `PieChart`, y `flet-charts` no es
una dependencia del proyecto. Se usan `Container`, `ResponsiveRow` y
`ProgressBar`; no se agregó ninguna librería.

## Roles, seguridad y consultas

Antes de consultar, `puede_consultar()` valida usuario, rol y pertenencia del
evento a `eventos_permitidos`. Master, Administrador, Operador y Consulta pueden
leer; un usuario sin acceso recibe `forbidden` sin ejecutar consultas. Las dos
lecturas filtran por cuenta y evento. No hay cliente global ni escrituras.

## Estados y actualización

Se cubren carga, error con reintento, sin evento (con acción de selección), sin
invitados, sin mesas, sin inicio y sin llegadas. La fase informa pre-evento,
evento en proceso o evento finalizado. Existe botón Actualizar e indicador
horario. La recarga ocurre al entrar, cambiar de evento, invalidar datos y por el
controlador existente cada 30 segundos; evita duplicados y se cancela al salir.

## Pruebas y limitaciones

`scripts/test_dashboard.py` cubre métricas, ceros, intervalos, límites, zona
horaria, cuatro roles, denegación antes de consultar, número de consultas,
componentes, breakpoints y estados. `scripts/test_dashboard_navigation.py`
mantiene la regresión de navegación.

La validación visual con datos remotos requiere una sesión autenticada y la
confirmación del usuario. Realtime permanece fuera de alcance.
