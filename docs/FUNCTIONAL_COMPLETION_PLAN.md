# Plan de finalización funcional de EventPlus

> Diseño 7A — importación Excel (2026-08-03): se auditó el esquema y se definió
> la futura importación atómica de mesas, invitaciones e invitados. El módulo
> sigue **no implementado**: no hay parser, UI, dependencia Excel ni RPC. La v1
> propuesta será FULL, Master/Admin, evento Activo/Pre_evento y completamente
> vacío. Véase `docs/EXCEL_IMPORT_DESIGN.md`.

> Actualización 2026-08-03: Dashboard real rediseñado con ocho KPI, afluencia en
> intervalos de 15 minutos, distribución de asistencia, progreso de mesas,
> estados vacíos y diseño responsive. El servicio valida acceso y usa dos
> lecturas sin N+1. Véase `docs/DASHBOARD_MODULE.md`. Realtime sigue pendiente.

> Actualización 2026-07-30: Administración de eventos implementada en FULL para
> Master/Administrador. Incluye CRUD lógico, ubicación validada, fases
> `Pre_evento → En_proceso → Post_evento`, predeterminado por usuario y pruebas.
> RPC/RLS siguen pendientes. Véase `docs/EVENTOS_ADMIN_MODULE.md`.

Estado de la auditoría: 29 de julio de 2026. Este documento describe el
repositorio local; no afirma el estado remoto de Supabase cuando no existe
evidencia exportada. No se ejecutó SQL ni se aplicó RLS durante esta auditoría.

> Esquema autoritativo: `C:\WORKSPACE\EVENTPLUS\esquema.sql`. El módulo usa los
> valores completos del CHECK. El default vigente `Otro` fue aplicado manualmente
> en Supabase el 2 de agosto de 2026 y es compatible con la restricción.

## 1. Resumen ejecutivo

EventPlus ya dispone de una base operativa probada para autenticar usuarios,
aislar clientes y sesiones por `Page`, restaurar sesiones web mediante cookie
opaca, calcular cuentas/eventos autorizados, seleccionar el evento activo,
consultar invitados y registrar o revertir llegadas. FULL y CHECKIN comparten
el mismo núcleo; CHECKIN restringe las operaciones de mantenimiento.

La brecha principal no está en el check-in, sino en preparar y administrar un
evento sin SQL Editor. No existen módulos funcionales para cuentas, lugares,
salones, eventos, mesas, usuarios o asignaciones. Invitaciones solo se leen
como apoyo de invitados y llegadas. El alta/edición de invitados existe fila a
fila, pero la importación masiva no existe. El Dashboard muestra contexto y
eventos disponibles, no las métricas de `evp_vw_evento_resumen`. Preferencias
es un placeholder. Tampoco existen Realtime, reportes, exportación ni
auditoría funcional.

RLS está auditada y diseñada, no aplicada. Las escrituras actuales de
invitados son operaciones directas de PostgREST protegidas por Python; antes
de despliegue público deben migrar a RPC transaccionales y probarse con RLS.
La sesión server-side ASGI usa un repositorio en memoria, por lo que pierde
sesiones al reiniciar y no sirve aún para escalado horizontal.

## 2. Criterios de clasificación

- **Implementado y probado:** servicio y flujo visible con pruebas automatizadas.
- **Implementado parcialmente:** existe una parte útil, pero falta el flujo completo.
- **Solo lectura:** consulta disponible, sin mantenimiento.
- **Solo existe en base de datos:** tabla/vista documentada sin módulo Python/UI.
- **Depende de carga manual:** la aplicación consume datos que deben prepararse fuera.
- **No implementado:** no hay servicio ni pantalla funcional.
- **Obsoleto:** artefacto histórico que no forma parte del runtime principal.
- **Requiere aclaración funcional:** faltan reglas para diseñar con seguridad.

## 3. Inventario funcional real

| # | Módulo/capacidad | Clasificación | Evidencia y límite real |
|---:|---|---|---|
| 1 | Autenticación | Implementado y probado | Google OAuth desktop, web y Android; intercambio Supabase, control de `state`, timeout, cancelación y rechazo de callbacks tardíos. `app_publishable_key_v4.py` queda como prueba histórica, no como runtime. |
| 2 | Sesiones | Implementado y probado / parcial para producción | Cliente Supabase por `Page`, refresh coordinado, logout local, ASGI, cookie HttpOnly y sesión server-side probados. El repositorio ASGI es solo `InMemorySessionRepository`. |
| 3 | Selección de cuenta | Implementado parcialmente | El contexto elige cuenta predeterminada o primera autorizada. La UI selecciona eventos y el encabezado muestra cuenta; no hay selector independiente ni mantenimiento del default. |
| 4 | Selección de evento | Implementado y probado | Dashboard lista eventos permitidos, permite activar uno y sincroniza sesión. Operador/Consulta solo reciben asignados. |
| 5 | Dashboard | Implementado parcialmente | Muestra cuenta, evento, fase, rol y cantidades de accesos. No consume `evp_vw_evento_resumen`, mesas ni estadísticas de invitados. |
| 6 | Invitados | Implementado y probado | Consulta paginada, filtros, búsqueda por nombre/mesa, detalle, alta/edición planificada en Pre-evento e inactivación de imprevistos. No hay baja de planificados, edición masiva ni auditoría visible. |
| 7 | Invitaciones | Solo lectura / carga manual | Se listan para formularios y se consulta el grupo durante llegadas. No hay alta, edición, desactivación ni pantalla propia. |
| 8 | Registro de llegadas | Implementado y probado | Confirmación individual desde Invitados y flujo dedicado en Llegadas; solo evento Activo/`En_proceso` y roles operativos. Escritura directa pendiente de RPC/RLS. |
| 9 | Reversión de llegadas | Implementado y probado | Reversión individual con revalidación de fase/estado. Falta confirmación modal explícita verificable y RPC transaccional. |
| 10 | Llegadas grupales | Implementado y probado / no atómico | Selección por invitación y confirmación parcial. El propio diseño reconoce que puede confirmar unas filas y omitir otras. |
| 11 | Invitados imprevistos | Implementado y probado | Alta e inactivación en `En_proceso`; deshabilitado en CHECKIN por regla actual. Requiere RPC y aclarar si CHECKIN debe permitirlo. |
| 12 | Mesas | Solo lectura indirecta / carga manual | La búsqueda obtiene IDs distintos desde `evp_ivt_invitado`; no consulta `evp_mes_mesa`, no muestra nombres reales ni mantiene mesas. |
| 13 | Lugares | Implementado y probado | Módulo FULL para Master/Admin: listado, alta, edición y cambio de estado por cuenta; sin DELETE. |
| 14 | Salones | Implementado y probado | Administración dentro del lugar, capacidades, aislamiento tenant y bloqueo por eventos abiertos. |
| 15 | Países | Solo existe en base de datos | Catálogo `evp_pai_pais`; sin servicio/UI. RLS SELECT autenticado está diseñada. |
| 16 | Cuentas | Solo lectura en contexto / carga manual | Se leen cuentas autorizadas. No hay alta, edición o desactivación. Crear cuenta debe ser decisión Master. |
| 17 | Eventos | Solo lectura y selección / carga manual | `evento_service` consulta eventos; no crea, edita, cambia fase/estado ni cierra eventos. |
| 18 | Usuarios | Solo lectura de identidad / carga manual | Se consulta al usuario autenticado por UUID/email. Preregistro, edición y estado se manejan fuera de la app. |
| 19 | Usuario-cuenta | Solo lectura / carga manual | Construye cuentas y roles activos. No administra relaciones o roles. |
| 20 | Usuario-evento | Solo lectura / carga manual | Determina eventos de Operador/Consulta. No administra asignaciones. |
| 21 | Roles y capacidades | Implementado y probado | Modelo central para Master, Administrador, Operador y Consulta. Consulta es estrictamente de lectura. La administración de roles no existe. |
| 22 | Preferencias | No implementado | El menú abre un placeholder. Defaults existen en `evp_usr_usuario`, con triggers documentados, pero no hay servicio de cambio. |
| 23 | Reportes | No implementado | No hay consultas, vistas de reporte, UI ni archivos generados. |
| 24 | Realtime | No implementado | `evp_ivt_invitado` está documentada como objetivo/publicación, pero el código no crea suscripciones. El estado remoto debe validarse. |
| 25 | Auditoría | Implementado parcialmente en trazas técnicas | Hay `print` de diagnóstico y columnas de auditoría en invitados. No existe bitácora funcional, consulta de cambios ni retención estructurada. |
| 26 | Carga masiva | No implementado | No hay parser, staging, validación, preview ni RPC de importación. |
| 27 | Exportación | No implementado | No hay CSV/XLSX/PDF ni servicio de exportación. |
| 28 | Operaciones administrativas | No implementado | No existe drawer/módulo administrativo pese a aparecer como alcance histórico. |
| 29 | Configuración del evento | No implementado | Lugar, salón, fechas, tipo, fase, estado y cierre dependen de carga manual. |
| 30 | FULL / CHECKIN | Implementado y probado | FULL ofrece Dashboard, Invitados y Llegadas según capacidad. CHECKIN inicia en Llegadas, limita navegación y bloquea mantenimiento de invitados; Consulta no ve Llegadas. |

### Módulos completos en el alcance actual

Autenticación multientorno, aislamiento de cliente por `Page`, ciclo de sesión,
ASGI/cookie opaca, contexto de autorización, selección de evento, consulta de
invitados, búsqueda por nombre/mesa, detalle, roles/capacidades y operaciones
de llegada están implementados y cubiertos por pruebas. “Completo” aquí no
significa listo para Internet: las mutaciones aún necesitan RPC y RLS.

### Artefactos obsoletos o históricos

`app_publishable_key_v4.py` es la prueba histórica de OAuth indicada por la
documentación y no forma parte de `app.py`. Las funciones
`_consultar_eventos_asignados_operador` y `get_supabase_client` se conservan
como compatibilidad; el runtime usa las variantes general y por-`Page`.

## 4. Matriz tabla / pantalla / servicio

“Roles” diferencia el acceso funcional previsto del control remoto actual:
RLS todavía no está aplicada.

| Tabla real | Propósito y dependencias | Consulta UI | Alta / edición / baja UI | Servicio Python | Roles funcionales | Carga actual | RPC | RLS / pruebas |
|---|---|---|---|---|---|---|---|---|
| `evp_usr_usuario` | Usuario interno; vincula `auth.users`; defaults a cuenta/evento | Solo propio durante login/contexto; sin pantalla | No / no / no | `usuario_service`, `session_service` | Propio; Master para administración futura | Manual preregistro + trigger Auth | Sí para preregistro, estado y defaults | SELECT diseñada; pruebas de login/contexto/sesión. Faltan CRUD, rol y aislamiento administrativo. |
| `evp_cta_cuenta` | Raíz tenant | Nombre en encabezado/Dashboard y contexto | No / no / no | `usuario_service` | Master todas; relacionados leen | Manual | Recomendable para alta; edición puede ser RPC o UPDATE muy restringido | SELECT/UPDATE Master diseñadas; faltan pruebas CRUD/tenant. |
| `evp_ucu_usuario_cuenta` | Relación usuario-cuenta, rol y estado; depende de usuario/cuenta | Solo contexto del propio usuario | No / no / no | `usuario_service`, `authorization_service` | Master/Admin según reglas pendientes; propio lee | Manual | Sí, por elevación de privilegios y reglas de autoasignación | Políticas propuestas; pruebas actuales solo consumen relación. |
| `evp_pai_pais` | Catálogo independiente | No | No / no / no | Ninguno | Autenticado lee; mantenimiento fuera del MVP | Manual/preexistente | No para lectura; mantenimiento controlado si se habilita | SELECT diseñada; sin pruebas. |
| `evp_lug_lugar` | Lugar por cuenta; depende de cuenta y opcionalmente país | No | No / no / no | Ninguno | Master/Admin escriben; roles autorizados leen | Manual | Directo viable con RLS, RPC recomendable si combina salón | RLS propuesta; sin pruebas. |
| `evp_sal_salon` | Salón por cuenta/lugar | No | No / no / no | Ninguno | Master/Admin escriben; roles autorizados leen | Manual | RPC recomendable al crear junto con lugar; directo viable aislado | RLS propuesta; sin pruebas. |
| `evp_eve_evento` | Evento por cuenta; depende de lugar/salón | Lista/selección y datos básicos | No / no / no | `evento_service`, `usuario_service`, `evento_context_service` | Master/Admin mantienen; Operador/Consulta asignados leen | Manual | Sí para creación/configuración coherente; transición de fase debe ser RPC | SELECT y mutación admin diseñadas; pruebas solo lectura/selección/fase operativa. |
| `evp_uev_usuario_evento` | Asignación usuario-evento; depende de usuario, cuenta y evento | Solo contexto propio | No / no / no | `usuario_service` | Master/Admin administran; asignado lee | Manual | Sí para evitar autoasignación y relación cuenta/rol inválida | RLS propuesta; pruebas de alcance Consulta/Operador, no CRUD. |
| `evp_mes_mesa` | Mesas por evento | No; solo se infieren IDs desde invitados | No / no / no | Ninguno directo | Master/Admin mantienen; usuarios del evento leen | Manual | Sí para generación masiva; directo viable para una mesa | RLS propuesta; faltan servicio, UI, nombres, capacidad y todas las pruebas CRUD. |
| `evp_inv_invitacion` | Cabecera/grupo de invitación; depende de evento | Lectura auxiliar en formularios y llegadas | No / no / no | `invitado_service` | Master/Admin mantienen; usuarios del evento leen | Manual | Recomendable; necesaria si se crea con invitados en una transacción | SELECT/mutación admin diseñadas; pruebas de listado/grupo, faltan CRUD. |
| `evp_ivt_invitado` | Invitados; depende de invitación y opcionalmente mesa | Sí: listado, búsqueda, filtros, detalle y llegada | Sí / sí / baja lógica solo imprevisto | `invitado_service` | Master/Admin planificados; Master/Admin/Operador operaciones; Consulta lee | Manual o formulario fila a fila | Sí para todas las mutaciones antes de producción | RLS SELECT diseñada y mutación revocada hasta RPC; amplia suite existente, faltan transacciones/RLS reales. |

Vistas reales relacionadas:

- `evp_vw_mesa_resumen`: solo existe en base documentada; sin consumo Python.
- `evp_vw_evento_resumen`: solo existe en base documentada; el Dashboard no la usa.
- Ambas requieren validar `security_invoker` o revocar exposición antes de RLS.

## 5. Flujos administrativos faltantes

| Flujo | Roles propuestos | Validaciones y tablas | Atomicidad / RPC | Riesgo | Prioridad |
|---|---|---|---|---|---:|
| Crear cuenta | Master | Nombre/contacto, suscripción, vencimiento y estado; `evp_cta_cuenta` | Una fila; RPC recomendable para autoridad Master y auditoría | Crear tenant o suscripción ilegítima | P1 |
| Editar/desactivar cuenta | Master | No mover ID; estado/suscripción; impedir desactivar con operación activa sin confirmación | RPC para desactivación y cascada lógica decidida | Bloqueo global de usuarios/eventos | P1 |
| Crear evento | Master/Admin de cuenta | Cuenta autorizada, lugar/salón compatibles, fechas, tipo, estado; `evp_eve_evento` | RPC recomendada; transaccional si crea configuración inicial | Evento en tenant o salón ajeno | P1 |
| Cambiar fase/estado | Master/Admin | Máquina de estados, fechas y pendientes; `evp_eve_evento` | RPC obligatoria para transición | Habilitar llegadas fuera de tiempo o reabrir cerrado | P0/P1 |
| Crear lugar/salón | Master/Admin | Misma cuenta, país válido, capacidad no negativa; `evp_lug_lugar`, `evp_sal_salon` | RPC si se crean juntos; transacción | Referencias cruzadas entre cuentas | P1 |
| Crear mesas | Master/Admin | Evento `Pre_evento`, nombres únicos, capacidad; `evp_mes_mesa` | RPC masiva transaccional | IDs relativos, duplicados, parcialidad | P1 |
| Crear invitaciones | Master/Admin | Evento `Pre_evento`, destinatario, código único, puestos; `evp_inv_invitacion` | RPC recomendada | Cupos incoherentes o código duplicado | P1 |
| Crear invitados | Master/Admin | Evento/invitación/mesa coherentes, duplicado normalizado, principal único | RPC; transacción con invitación cuando aplique | Escribir en otro tenant, exceder cupos | P0 existente / P1 endurecimiento |
| Preregistrar usuario | Master y, si se aprueba, Admin limitado a su cuenta | Email normalizado único, estado `Preregistrado`, no aceptar Auth UUID/master del cliente | RPC obligatoria | Escalación a Master, apropiación de identidad | P1 |
| Asignar usuario a cuenta | Master/Admin según regla pendiente | Usuario/cuenta activos, rol permitido, no autoelevarse; `evp_ucu_usuario_cuenta` | RPC obligatoria | Escalación de rol y acceso tenant | P1 |
| Asignar usuario a evento | Master/Admin de cuenta | Relación cuenta previa, solo Operador/Consulta, evento de misma cuenta | RPC obligatoria | Autoasignación o acceso cruzado | P1 |
| Asignar rol | Master/Admin según gobierno por definir | Solo Administrador/Operador/Consulta; proteger Master; historial | RPC obligatoria | Escalación de privilegios | P1 |
| Activar/desactivar usuarios/relaciones | Master/Admin según alcance | No revocar último administrador sin regla; coherencia de defaults | RPC obligatoria, transacción si limpia relaciones/defaults | Bloqueo o persistencia de acceso | P1 |
| Cambiar evento predeterminado | Usuario sobre evento autorizado; Admin opcional | Cuenta/evento autorizados y activos; `evp_usr_usuario` | RPC breve recomendada, o función existente auditada | Fijar default no autorizado | P2 |
| Importar invitados | Master/Admin | Archivo, columnas, encoding, preview, duplicados, invitación/mesa/cupo | RPC o proceso server-side transaccional por lote; staging recomendado | Parcialidad, inyección de IDs, datos sensibles | P1 |
| Corregir datos antes del evento | Master/Admin | Solo `Pre_evento`, auditoría, restricciones únicas | RPC para cambios sensibles; operaciones simples pueden reutilizar RPC CRUD | Corrupción poco antes del evento | P1 |
| Cerrar evento | Master/Admin autorizado | Fase válida, pendientes advertidos, timestamp/regla de reapertura | RPC obligatoria | Pérdida de operación o reapertura indebida | P1 |

Decisiones funcionales pendientes antes de implementar usuarios: si un
Administrador puede crear otros Administradores, revocar a un par o al último
Administrador, y quién puede reabrir un evento Cerrado.

## 6. Operaciones que requieren RPC

| Operación | Clasificación recomendada | Columnas sensibles | Roles | Validaciones server-side |
|---|---|---|---|---|
| Llegada individual | Convertir a RPC transaccional | tenant/evento/invitación/invitado, fecha y usuario de llegada | Master/Admin/Operador | Identidad desde JWT, asignación, fase/estado real, pendiente, bloqueo de fila, timestamp SQL. |
| Llegada grupal | RPC obligatoria y atómica | Las anteriores para todos los UUID | Master/Admin/Operador | Misma invitación/evento, lista no vacía, `FOR UPDATE`, todo-o-nada o contrato explícito de parcialidad. |
| Reversión | RPC obligatoria | Estado, timestamp y usuario de llegada | Master/Admin/Operador, sujeto a regla | Confirmada, fase permitida, motivo/auditoría si se exige, concurrencia. |
| Invitado imprevisto | RPC obligatoria | tenant/evento/invitación, flags, IDs relativos, creador | Master/Admin/Operador según decisión CHECKIN | Evento operativo, duplicado, invitación/cupo, identidad del creador. |
| Crear planificado | RPC recomendada antes de RLS | tenant/evento/invitación, principal, mesa/puesto, auditoría | Master/Admin | `Pre_evento`, unicidad normalizada, principal único, FK de mismo tenant. |
| Editar invitado | RPC recomendada antes de RLS | No permitir mover tenant/evento/invitación ni auditoría | Master/Admin | `Pre_evento`, registro actual, duplicado y concurrencia. |
| Crear usuario y asignaciones | RPC obligatoria y transaccional | master, Auth UUID, estado, rol, cuenta/evento | Master/Admin limitado | Email, gobierno de roles, relación y defaults; nunca aceptar master/Auth UUID arbitrarios. |
| Cambiar roles | RPC obligatoria | `ucu_rol`, estado y actor | Master/Admin según decisión | No autoelevar, no tocar Master, no dejar cuenta sin administración. |
| Crear evento | RPC recomendada | cuenta, IDs relativos, fase/estado, lugar/salón | Master/Admin | Tenant, FK compuestas, fechas y valores; fase inicial segura. |
| Crear mesas masivas | RPC obligatoria y transaccional | cuenta/evento/IDs/nombres | Master/Admin | `Pre_evento`, cantidad máxima, nombres únicos, rollback total. |
| Importar invitados | RPC/proceso server-side obligatorio | Todas las columnas de tenant, IDs y auditoría | Master/Admin | Preview firmado, límites, duplicados, cupos, FK, lote idempotente y reporte de errores. |

Las lecturas de catálogos, cuentas autorizadas, eventos asignados, mesas,
invitaciones e invitados pueden continuar como SELECT directo con RLS. Una
actualización directa simple solo sería aceptable donde no haya escalación,
IDs sensibles ni invariantes cruzadas; en EventPlus casi todas las mutaciones
administrativas afectan esas condiciones.

## 7. Mapa de dependencias real

```text
evp_pai_pais
      └─> evp_lug_lugar
evp_cta_cuenta
      ├─> evp_lug_lugar ─> evp_sal_salon
      │                         └─> evp_eve_evento
      ├────────────────────────────> evp_eve_evento
      │                                  ├─> evp_mes_mesa
      │                                  ├─> evp_inv_invitacion
      │                                  │       └─> evp_ivt_invitado
      │                                  └─> evp_uev_usuario_evento
      └─> evp_ucu_usuario_cuenta                 ^
evp_usr_usuario ─────────────────────────────────┘
      └─> evp_ucu_usuario_cuenta
```

Dependencias adicionales:

- Invitado depende de invitación; mesa es opcional según el contrato.
- Lugar y salón deben pertenecer a la misma cuenta del evento.
- Usuario-evento requiere usuario-cuenta previo y solo es necesario para
  Operador/Consulta.
- Defaults de usuario dependen de relaciones válidas y no deben ser autoridad.

### Paralelismo seguro

- Servicio/UI de países puede desarrollarse junto con diseño de cuentas.
- Cuenta y gobierno de usuarios pueden diseñarse en paralelo, pero las
  asignaciones necesitan cuentas creadas.
- Lectura de resumen de evento/mesa puede avanzar en paralelo con CRUD de
  lugares/salones porque es SELECT.
- Diseño del importador puede avanzar con fixtures locales, pero no persistir
  hasta cerrar contratos de invitación, mesas y RPC.

### Bloqueos

- Eventos nuevos están bloqueados por cuenta, lugar y salón.
- Mesas e invitaciones están bloqueadas por evento.
- Invitados están bloqueados por invitación y, si se asignan puestos, mesas.
- Usuario-evento está bloqueado por usuario, usuario-cuenta y evento.
- Realtime y reportes fiables dependen de RLS SELECT y de una fuente de cambios
  segura.

### Relación con RLS

Antes de RLS de escritura deben existir las RPC de llegadas, invitados,
transiciones de evento, roles/asignaciones e importación. RLS SELECT puede
probarse gradualmente primero en país, cuenta/evento, y después mesas,
invitaciones e invitados. Cada etapa requiere metadatos remotos, JWT de prueba
por rol y rollback; no se debe activar la migración integral de una vez.

## 8. Estrategia de pruebas para módulos pendientes

Todos los módulos deben incluir:

- unitarias para normalización, validaciones y máquina de estados;
- servicio con cliente falso y respuestas vacías/error/concurrencia;
- matriz Master/Administrador/Operador/Consulta, con Consulta solo lectura;
- construcción UI en loading/empty/ready/error/saving;
- aislamiento entre cuenta A/B y evento A1/A2;
- negativas por IDs adulterados, rol, estado, fase y duplicados;
- transacción/rollback cuando intervengan varias filas;
- manual responsiva en móvil, tablet y desktop;
- prueba RLS posterior con JWT real, nunca `service_role`.

Pruebas específicas faltantes:

| Módulo | Pruebas imprescindibles |
|---|---|
| Cuenta | Master crea/edita/desactiva; Admin/Operador/Consulta denegados; tenant inmutable; vencimiento/estado. |
| País/lugar/salón | catálogo vacío/error; Admin solo su cuenta; país y lugar válidos; capacidades no negativas; Consulta sin botones. |
| Evento | FK misma cuenta, fechas, fase inicial, transiciones válidas/ilegales, cierre, Admin A no toca B, Consulta lee. |
| Mesas | una y lote, nombres/IDs únicos, máximo del salón, rollback total, Consulta lee nombres/resumen. |
| Invitaciones | código único, cupos, estado, CRUD Pre-evento, aislamiento, Consulta lee. |
| Usuarios/asignaciones | email normalizado, preregistro, trigger Auth, no autoelevación, último Admin, Operador/Consulta requieren evento. |
| Preferencias | solo defaults autorizados, relación inactiva, cambio concurrente, persistencia de sesión. |
| Importación | formatos/encoding, preview, filas inválidas, duplicados internos/BD, idempotencia, lote grande, rollback/reporte. |
| Realtime | dos sesiones/tres roles, tenant cruzado, métricas, reconexión, no alterar formulario abierto. |
| Reportes/exportación | filtros, totales, timezone, escaping CSV, límites, PII y autorización. |

## 9. Prioridades P0-P3

### P0 — indispensable para operar y publicar con seguridad

1. Convertir llegada individual, grupal, reversión e imprevistos a RPC.
2. Convertir alta/edición de invitados existentes a RPC o bloquearlas al
   activar RLS.
3. Validar metadatos remotos y probar RLS SELECT por etapas.
4. Definir transición de fase/estado y cierre de evento.
5. Sustituir sesiones ASGI en memoria antes de múltiples instancias o aceptar
   explícitamente despliegue de una instancia con pérdida al reiniciar.

### P1 — administrar sin SQL manual

1. Lugares y salones. **Implementado localmente; RLS remota pendiente.**
2. Eventos y configuración/fases.
3. Mesas.
4. Invitaciones.
5. Importación de invitados.
6. Usuarios, roles y asignaciones.
7. Cuentas administradas por Master.

En una instalación desde cero, cuentas preceden a lugares. En el entorno
actual ya existen cuentas operativas, por lo que el primer incremento visible
puede empezar en lugares/salones sin bloquearse.

### P2 — preparación de producción

1. Preferencias/defaults.
2. Dashboard real con vistas de resumen.
3. Realtime seguro.
4. Exportación y reportes operativos.
5. Auditoría funcional y observabilidad.
6. Persistencia compartida de sesiones, backups y operación multiinstancia.

### P3 — mejoras posteriores

1. Reportes avanzados e históricos.
2. Flujos de novedades completos.
3. Automatizaciones de invitaciones/QR y comunicaciones.
4. Personalización visual y optimizaciones avanzadas.

## 10. Roadmap incremental

Cada bloque entrega UI visible, servicio, SQL propuesto, pruebas y criterios de
aceptación sin activar RLS globalmente.

| Bloque | Entrega visible | Dependencias | Criterio de aceptación |
|---:|---|---|---|
| 0 | RPC del check-in actual | Reglas de fase/roles | Los flujos actuales pasan contra RPC; grupo atómico; Consulta y tenant cruzado denegados; SQL/rollback propuestos. |
| 1 | Catálogo de lugares y salones por cuenta | Cuentas existentes y países | Master/Admin CRUD en su cuenta; Operador/Consulta solo consulta; FK/capacidades; pruebas UI/servicio/roles. |
| 2 | Administración Master de cuentas | Gobierno Master definido | Alta/edición/desactivación sin SQL; IDs inmutables; Admin/Consulta denegados; rollback. |
| 3 | Crear/configurar/cerrar eventos | Cuenta + lugar + salón | Admin crea en su cuenta; fases válidas; Consulta lee; no mover tenant; RPC y pruebas. |
| 4 | Administrar mesas | Evento Pre-evento | CRUD y creación masiva atómica; nombres visibles en búsqueda; aislamiento. |
| 5 | Administrar invitaciones | Evento Pre-evento | CRUD, códigos/cupos; lectura por roles; ninguna mutación de Consulta. |
| 6 | Importar invitados | Invitaciones + mesas + RPC invitados | Preview, validación, idempotencia, lote transaccional y reporte descargable. |
| 7 | Administrar usuarios y asignaciones | Cuentas/eventos + gobierno de roles | Preregistro y relaciones sin SQL; no autoelevación; Consulta solo lectura. |
| 8 | Preferencias y Dashboard real | Lecturas estables | Defaults autorizados y métricas de vistas validadas con RLS SELECT. |
| 9 | Realtime, exportación y auditoría | RLS SELECT + RPC | Dos sesiones reciben cambios sin fuga; exportaciones autorizadas; trazabilidad. |

## 11. Próximo módulo recomendado

### Lugares y salones por cuenta

Es el siguiente incremento funcional recomendado, después de mantener como
trabajo P0 el endurecimiento RPC del check-in existente.

Razones:

1. Elimina una carga manual recurrente y acotada.
2. Es dependencia directa para crear eventos.
3. Usa tablas y triggers ya existentes, sin cambio de esquema.
4. Permite probar Master y Administrador en escritura, y Operador/Consulta en
   lectura, incluida la ausencia de controles de mutación.
5. Prepara helpers, filtros tenant y políticas SELECT/WRITE reutilizables.
6. Puede entregarse y probarse sin implementar todavía eventos ni activar RLS.

Criterios de aceptación del primer bloque:

- lista lugares de la cuenta actual y sus salones;
- Master/Admin crean, editan e inactivan solo dentro de la cuenta autorizada;
- Consulta y Operador pueden leer únicamente cuando su acceso de cuenta/evento
  lo justifique, sin botones ni llamadas de escritura;
- valida país, tipo, nombres, capacidades y relación salón-lugar-cuenta;
- omite IDs relativos para que los triggers los generen;
- maneja loading/empty/ready/error/saving y concurrencia básica;
- incluye SQL/RLS propuestos y rollback, sin aplicación remota;
- cubre servicio, UI, roles, aislamiento A/B y casos negativos.

Archivos previstos para la próxima tarea:

- nuevos `services/lugar_service.py` y `views/lugares_view.py`;
- componentes reutilizables de formulario/listado si resultan necesarios;
- `views/home_view.py`, `components/bottom_navigation.py` o un menú
  administrativo para integrar el destino;
- `services/authorization_service.py` para capacidades específicas de catálogo;
- nuevos scripts `test_lugares_salones.py`;
- migración/RLS propuesta y rollback bajo `supabase/migrations/`;
- contexto, esquema, diagnóstico y este roadmap.

No se debe modificar autenticación, OAuth, cookies ni ASGI para ese bloque.
# Actualización Tarea 7B (2026-08-03)

La plantilla, lectura segura, validación completa, vista previa y archivo de
errores Excel están implementados en FULL. Queda pendiente la validación manual
del usuario y la importación RPC transaccional de 7C; no hubo escrituras en 7B.
# Actualización Tarea 7C (2026-08-04)

Migración RPC, rollback, contrato versionado, servicio Python y UI de
confirmación preparados. Pendientes: aplicar la migración, pruebas SQL aisladas
y prueba manual de importación/rollback/concurrencia.
