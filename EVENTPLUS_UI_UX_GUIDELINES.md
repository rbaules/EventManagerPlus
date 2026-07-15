# EVENTPLUS_UI_UX_GUIDELINES.md

## 1. Propósito de este archivo

Este archivo define los lineamientos de **usabilidad, diseño visual, experiencia de usuario y buenas prácticas de interfaz** que deben aplicarse en EventPlus.

Codex debe leer este archivo antes de crear o modificar pantallas Flet.

Este documento complementa:

- `EVENTPLUS_CONTEXT.md`
- `EVENTPLUS_SCHEMA_CONTEXT_v1_1.md`

La prioridad es que EventPlus sea:

- Profesional
- Claro
- Rápido de usar
- Responsivo
- Amigable para escritorio, tablet y móvil
- Cómodo para uso en eventos reales, donde el operador necesita actuar rápido

---

## 2. Referencia de inspiración

Referencia visual/conceptual:

```text
Video: Create PROFESSIONAL Apps with Python in 200 Lines
Tema: interfaces modernas y reactivas con Python + Flet
```

Ideas principales a aplicar en EventPlus:

- Construir interfaces limpias y profesionales sin sobrecargar la pantalla.
- Usar componentes reutilizables.
- Separar lógica, servicios y vistas.
- Crear pantallas responsivas.
- Diseñar interfaces reactivas que cambien visualmente según el estado de la app.
- Aprovechar controles modernos de Flet en lugar de crear diseños rígidos.
- Priorizar claridad, navegación simple y feedback inmediato.

---

## 3. Principios generales de UX

Codex debe aplicar estos principios en todas las pantallas:

### 3.1 Visibilidad del estado del sistema

La app siempre debe mostrar al usuario qué está ocurriendo.

Ejemplos:

- Mostrar indicador de carga al consultar Supabase.
- Mostrar texto como `Cargando invitados...`.
- Mostrar confirmación visual cuando se registra una llegada.
- Mostrar mensaje claro si no hay conexión o si Supabase devuelve error.
- Mostrar estado actual del evento: `Pre_evento`, `En_proceso`, `Post_evento`, `Cerrado`.

### 3.2 Prevención de errores

La interfaz debe evitar acciones equivocadas antes de que ocurran.

Ejemplos:

- No mostrar botón `Confirmar llegada` si el invitado ya está confirmado.
- No permitir confirmar llegada si el evento no está en fase `En_proceso`, salvo reglas explícitas.
- Pedir confirmación antes de desmarcar una llegada.
- Deshabilitar botones mientras una operación está en proceso.
- Validar campos obligatorios antes de enviar a Supabase.

### 3.3 Reconocimiento antes que memoria

El usuario no debe recordar códigos internos.

Mostrar nombres claros:

- Nombre de cuenta
- Nombre del evento
- Nombre del salón
- Nombre del invitado
- Mesa
- Puesto
- Estado de llegada

Evitar mostrar IDs internos salvo en pantallas técnicas o de depuración.

### 3.4 Consistencia

Usar patrones visuales consistentes:

- Mismos colores para estados.
- Mismo estilo de botones primarios.
- Mismo patrón de tarjetas.
- Misma ubicación para navegación.
- Mismo formato de mensajes de error.
- Misma terminología en todas las pantallas.

### 3.5 Diseño minimalista

No saturar la pantalla.

Cada pantalla debe responder:

```text
¿Qué necesita hacer el usuario aquí?
¿Qué información necesita para hacerlo bien?
¿Qué acción principal debe ser más visible?
```

---

## 4. Contexto operativo de EventPlus

EventPlus será usado durante eventos reales. Eso implica:

- El operador puede estar de pie.
- Puede haber poca luz o luz intensa.
- Puede haber presión de tiempo.
- Puede haber filas de personas esperando.
- Puede usarse en laptop, tablet o teléfono.
- La búsqueda de invitados debe ser muy rápida.
- Los botones deben ser fáciles de tocar.
- Los textos deben ser legibles.
- La interfaz debe reducir la posibilidad de errores.

Por lo tanto:

- Priorizar velocidad.
- Priorizar claridad.
- Priorizar feedback inmediato.
- Evitar pantallas densas.
- Evitar pasos innecesarios.

---

## 5. Diseño responsivo

Codex debe evitar diseños rígidos con anchos fijos.

Usar:

- `expand=True`
- `ft.ResponsiveRow`
- `col={...}`
- `ft.SafeArea`
- `ft.ListView`
- `scroll=ft.ScrollMode.AUTO`
- `page.on_resize` cuando sea necesario
- navegación adaptativa según ancho

### 5.1 Breakpoints sugeridos

Usar estos puntos de referencia:

```text
Compacto / móvil:      ancho < 600 px
Mediano / tablet:      600 px <= ancho < 1024 px
Amplio / desktop:      ancho >= 1024 px
```

### 5.2 Comportamiento en móvil

En pantallas pequeñas:

- Usar una sola columna.
- Usar `NavigationBar` inferior para destinos principales.
- Evitar tablas anchas.
- Mostrar invitados como tarjetas/lista.
- Mantener botones grandes.
- Usar búsqueda visible y fija cerca del inicio.
- Evitar sidebars permanentes.

### 5.3 Comportamiento en tablet

En pantallas medianas:

- Usar dos columnas cuando aporte valor.
- Mostrar resumen del evento arriba.
- Mostrar lista de invitados debajo.
- Usar tarjetas compactas.
- Puede usarse `NavigationRail` si el ancho lo permite.

### 5.4 Comportamiento en desktop

En pantallas amplias:

- Usar `NavigationRail` o panel lateral.
- Mostrar contenido en tarjetas o paneles.
- Permitir tabla/listado más denso.
- Mostrar resumen del evento en la parte superior.
- Mantener ancho máximo razonable para lectura.
- No estirar formularios de forma innecesaria.

---

## 6. Navegación recomendada

La app debe usar navegación simple y predecible.

### 6.1 Flujo inicial

```text
Login
→ Cargar usuario EventPlus
→ Seleccionar cuenta/evento si aplica
→ Home del evento
→ Invitados
→ Confirmación de llegada
```

### 6.2 Destinos principales

Destinos iniciales sugeridos:

```text
Inicio
Invitados
Mesas
Resumen
Configuración / Preferencias
```

No todos deben existir en la primera versión, pero la estructura debe permitirlos.

### 6.3 Navegación adaptativa

Usar:

- `NavigationBar` en móvil.
- `NavigationRail` en desktop/tablet.
- `NavigationDrawer` si se requiere menú adicional.

Regla:

```text
No duplicar navegación innecesariamente.
No crear pantallas flotantes si una vista normal resuelve el caso.
```

---

## 7. Layout base recomendado

Cada pantalla debe seguir una estructura similar:

```text
SafeArea
└── App Shell
    ├── Navegación adaptativa
    └── Contenido principal
        ├── Encabezado
        ├── Resumen / métricas clave
        ├── Controles de búsqueda/filtro
        ├── Contenido principal
        └── Mensajes / acciones
```

### 7.1 AppBar / encabezado

Debe mostrar:

- Nombre de la pantalla.
- Nombre del evento actual cuando aplique.
- Usuario actual o menú de usuario.
- Acción principal si aplica.

Ejemplo:

```text
Invitados — Boda María y José
Cuenta: Demo Eventos
Estado: En proceso
```

---

## 8. Sistema visual

### 8.1 Estilo general

EventPlus debe verse:

- Moderno
- Profesional
- Limpio
- Confiable
- Sin exceso de colores
- Sin sombras exageradas
- Sin elementos decorativos innecesarios

### 8.2 Paleta sugerida

Usar una paleta sobria con un color principal inspirado en verde tipo WhatsApp/EventPlus.

Sugerencia conceptual:

```text
Primario: verde EventPlus
Neutros: blanco, gris claro, gris medio, gris oscuro
Éxito: verde
Advertencia: ámbar/naranja
Error: rojo
Información: azul discreto
```

No usar demasiados colores compitiendo.

### 8.3 Modo claro y oscuro

Diseñar pensando desde el inicio en modo claro y oscuro.

Reglas:

- No hardcodear colores donde Flet pueda usar el tema.
- Usar colores semánticos.
- Probar contraste en ambos modos.
- Evitar texto gris muy claro sobre fondo blanco.
- Evitar verde brillante sobre fondo blanco si no cumple contraste.

### 8.4 Contraste

Los textos normales deben mantener contraste suficiente.

Regla de referencia:

```text
Texto normal: mínimo 4.5:1
Texto grande: mínimo 3:1
Componentes UI relevantes: mínimo 3:1
```

---

## 9. Tipografía

### 9.1 Jerarquía de texto

Usar niveles consistentes:

```text
Título de pantalla: 22-28 px
Subtítulo/sección: 16-20 px
Texto normal: 14-16 px
Texto auxiliar: 12-14 px
```

### 9.2 Reglas

- No usar demasiados tamaños distintos.
- Evitar párrafos largos en pantallas operativas.
- Usar textos claros y concretos.
- Evitar tecnicismos en interfaz visible al usuario final.
- No mostrar nombres técnicos de columnas.

Ejemplo:

Usar:

```text
Llegada confirmada
```

No usar:

```text
ivt_llegada_confirmada = true
```

---

## 10. Espaciado y composición

Usar una escala consistente basada en 8 px:

```text
4 px  = micro separación
8 px  = separación pequeña
16 px = separación estándar
24 px = separación entre secciones
32 px = separación amplia
```

Reglas:

- No pegar controles entre sí.
- No llenar todo el espacio por llenar.
- Agrupar información relacionada.
- Separar secciones visualmente.
- Usar tarjetas para información agrupada.

---

## 11. Componentes reutilizables recomendados

Codex debe preferir crear componentes reutilizables en lugar de repetir controles.

Componentes sugeridos:

```text
AppShell
LoginCard
SectionHeader
StatCard
EventSummaryCard
GuestSearchBar
GuestListItem
GuestStatusChip
EmptyState
LoadingState
ErrorBanner
ConfirmActionDialog
PrimaryActionButton
SecondaryActionButton
```

### 11.1 `StatCard`

Uso:

- Total invitados
- Llegadas confirmadas
- Pendientes
- Imprevistos
- Porcentaje de avance

Debe ser compacto y legible.

### 11.2 `GuestListItem`

Debe mostrar:

- Nombre del invitado
- Mesa y puesto
- Invitación/destinatario si aplica
- Estado de llegada
- Novedad si aplica
- Botón de acción principal

### 11.3 `GuestStatusChip`

Estados sugeridos:

```text
Pendiente
Confirmado
Con novedad
Imprevisto
Inactivo
```

---

## 12. Pantalla de Login

### 12.1 Objetivo

Permitir que el usuario se autentique con Google usando Supabase Auth.

### 12.2 Reglas

- Mostrar marca EventPlus.
- Mostrar texto breve explicando el acceso.
- Botón claro: `Iniciar sesión con Google`.
- Mostrar errores de configuración/autenticación de manera entendible.
- No mostrar detalles técnicos salvo en modo debug.

### 12.3 Contenido sugerido

```text
EventPlus
Control de entrada a eventos

Inicia sesión con tu cuenta autorizada.
[Iniciar sesión con Google]
```

### 12.4 Estados

Debe manejar:

```text
Listo
Abriendo navegador
Esperando autenticación
Validando usuario
Acceso concedido
Acceso no autorizado
Error de conexión
```

---

## 13. Home / selección de cuenta y evento

### 13.1 Objetivo

Después del login, mostrar al usuario las cuentas y eventos disponibles según sus permisos.

### 13.2 Reglas

- Si solo hay una cuenta y un evento disponible, permitir entrada directa.
- Si hay varias cuentas, mostrar selector de cuenta.
- Si hay varios eventos, mostrar selector de evento.
- Mostrar fase del evento.
- Mostrar fecha/hora del evento.
- No mostrar eventos inactivos salvo en modo consulta/administración.

### 13.3 Información mínima

```text
Nombre de cuenta
Nombre de evento
Fecha/hora
Fase
Estado
Rol del usuario
```

---

## 14. Pantalla de invitados

### 14.1 Objetivo

Permitir buscar invitados y confirmar llegadas rápidamente.

### 14.2 Prioridades

1. Búsqueda rápida.
2. Confirmación de llegada.
3. Visualizar estado.
4. Registrar novedad si aplica.
5. Agregar invitado imprevisto si el rol lo permite.

### 14.3 Layout recomendado

En móvil:

```text
Resumen compacto
Buscador
Lista de invitados como tarjetas
```

En desktop:

```text
Resumen de métricas
Buscador/filtros
Lista o tabla de invitados
Panel lateral opcional de detalle
```

### 14.4 Búsqueda

El buscador debe permitir:

- Nombre del invitado
- Nombre normalizado
- Mesa
- Invitación/destinatario, si está disponible

Reglas:

- El campo de búsqueda debe estar siempre visible.
- Debe responder rápido.
- Mostrar estado vacío si no hay resultados.
- Evitar que el usuario tenga que usar mayúsculas/tildes exactas.

### 14.5 Confirmar llegada

La acción debe ser clara:

```text
Confirmar llegada
```

Al confirmar:

- Deshabilitar botón mientras se actualiza.
- Mostrar confirmación visual.
- Actualizar estado del invitado.
- Mostrar fecha/hora de confirmación.
- Evitar doble clic.

---

## 15. Formularios

### 15.1 Reglas generales

- Agrupar campos relacionados.
- Marcar campos obligatorios.
- Validar antes de enviar.
- Mostrar errores junto al campo.
- Usar labels claros.
- No usar nombres técnicos de base de datos.
- No hacer formularios muy largos en una sola pantalla.

### 15.2 Botones

Usar jerarquía clara:

```text
Acción principal: botón destacado
Acción secundaria: botón outlined/text
Acción destructiva: botón con confirmación
```

Ejemplos:

```text
Guardar
Cancelar
Confirmar llegada
Registrar novedad
Agregar invitado
```

---

## 16. Estados de interfaz

Cada pantalla debe manejar explícitamente estos estados:

```text
loading
empty
ready
error
saving
success
offline/retry
```

### 16.1 Loading

Usar `ProgressRing`, `ProgressBar`, skeleton simple o mensaje.

No dejar la pantalla congelada sin feedback.

### 16.2 Empty state

Ejemplo:

```text
No hay invitados registrados para este evento.
```

Debe incluir acción si aplica:

```text
Agregar invitado
```

### 16.3 Error state

Debe incluir:

- Qué pasó.
- Qué puede hacer el usuario.
- Opción de reintentar si aplica.

No mostrar trazas técnicas al usuario final.

---

## 17. Tablas vs listas

### 17.1 En móvil

Evitar `DataTable` grande.

Usar tarjetas/listas.

### 17.2 En desktop

Se puede usar tabla si:

- Hay muchas filas.
- Las columnas son pocas y útiles.
- La tabla no requiere scroll horizontal excesivo.

### 17.3 Regla

Si una tabla se vuelve difícil de leer, convertir a:

```text
lista filtrable + detalle lateral
```

---

## 18. Accesibilidad

Codex debe considerar:

- Contraste suficiente.
- Tamaños de texto legibles.
- Botones fáciles de tocar.
- Estados no dependientes solo del color.
- Labels claros.
- Orden lógico de navegación.
- Mensajes de error entendibles.
- Uso de iconos acompañado de texto cuando la acción pueda ser ambigua.

### 18.1 Tamaños táctiles

Los botones y elementos tocables deben tener tamaño cómodo.

Referencia práctica:

```text
Altura mínima sugerida: 44-48 px
Separación entre elementos tocables: mínimo 8 px
```

---

## 19. Feedback y microinteracciones

Usar feedback visual sobrio:

- `SnackBar` para confirmaciones.
- Icono/chip de estado para llegada confirmada.
- Cambio de botón después de confirmar.
- Indicador de guardando.
- Mensaje claro cuando se actualiza desde realtime.

Evitar animaciones innecesarias.

---

## 20. Rendimiento percibido

EventPlus debe sentirse rápido.

Reglas:

- No recargar toda la app si solo cambia un invitado.
- Evitar consultas innecesarias.
- Usar filtros locales cuando el dataset ya está cargado y es pequeño.
- Usar consultas a Supabase para datasets grandes.
- Mostrar datos parciales mientras carga lo demás.
- Evitar reconstruir toda la pantalla si solo cambia un control.

---

## 21. Realtime UX

Cuando llegue una actualización realtime:

- Actualizar el invitado afectado.
- Actualizar métricas del resumen.
- No interrumpir al usuario.
- No cerrar diálogos abiertos.
- No borrar texto que el usuario está escribiendo.
- Mostrar una señal discreta si un registro fue actualizado por otro usuario.

Ejemplo:

```text
Actualizado por otro operador
```

---

## 22. Manejo de errores técnicos

Errores técnicos deben registrarse o mostrarse en modo desarrollo.

Para usuario final:

Usar mensajes como:

```text
No pudimos consultar los invitados. Revisa tu conexión e intenta nuevamente.
```

No usar:

```text
PostgREST error PGRST116
```

salvo pantalla debug.

---

## 23. Convenciones Flet

Codex debe preferir:

```python
page.adaptive = True
ft.SafeArea(...)
ft.ResponsiveRow(...)
ft.Container(...)
ft.Column(...)
ft.Row(...)
ft.ListView(...)
ft.NavigationBar(...)
ft.NavigationRail(...)
ft.SnackBar(...)
ft.AlertDialog(...)
```

Evitar:

- Posicionamiento absoluto innecesario.
- Anchos fijos rígidos.
- Altos fijos que rompan en pantallas pequeñas.
- Código duplicado de componentes.
- Mezclar demasiada lógica de Supabase dentro de la vista.

---

## 24. Arquitectura recomendada para UI

Separar:

```text
views/      pantallas Flet
services/   llamadas Supabase y lógica de negocio
components/ controles reutilizables
utils/      helpers generales
```

Estructura sugerida:

```text
views/login_view.py
views/home_view.py
views/evento_select_view.py
views/invitados_view.py

components/app_shell.py
components/stat_card.py
components/guest_list_item.py
components/status_chip.py
components/empty_state.py
components/error_banner.py
```

---

## 25. Reglas para Codex al crear pantallas

Antes de crear una pantalla, Codex debe responder internamente:

```text
¿Qué tarea principal resuelve esta pantalla?
¿Qué información mínima necesita el usuario?
¿Cuál es la acción principal?
¿Qué estados deben manejarse?
¿Cómo se verá en móvil?
¿Cómo se verá en desktop?
¿Qué componentes reutilizables se pueden usar?
```

---

## 26. Primera pantalla objetivo después del login

El siguiente objetivo de UI es crear:

```text
Home simple posterior al login
```

Debe mostrar:

- Nombre del usuario.
- Rol detectado.
- Cuenta default si existe.
- Evento default si existe.
- Botón para seleccionar evento.
- Botón para ir a invitados si ya hay evento activo.
- Mensaje si no tiene permisos o no hay eventos.

---

## 27. Criterio de aceptación UI para el MVP

Una pantalla cumple si:

- Se entiende sin explicación.
- No muestra errores técnicos al usuario final.
- Funciona en ancho móvil y desktop.
- Tiene estado loading.
- Tiene estado empty.
- Tiene estado error.
- Tiene acción principal visible.
- No usa nombres técnicos de BD en la interfaz.
- Usa colores y espaciado de forma consistente.
- No rompe el layout al redimensionar ventana.
- No requiere más clics de los necesarios.

---

## 28. Prioridad de diseño para EventPlus

Para este proyecto, la prioridad es:

```text
1. Claridad
2. Rapidez
3. Prevención de errores
4. Responsividad
5. Profesionalismo visual
6. Estética
```

La estética es importante, pero nunca debe dificultar la operación en el evento.
