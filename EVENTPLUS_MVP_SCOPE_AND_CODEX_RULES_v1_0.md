# EVENTPLUS_MVP_SCOPE_AND_CODEX_RULES_v1_0.md

## 1. Propósito de este archivo

Este archivo incorpora el documento **"EventPlus: Producto Mínimo Viable - versión 1.0"** dentro de las reglas que debe seguir Codex para desarrollar EventPlus.

Debe leerse junto con:

```text
EVENTPLUS_CONTEXT.md
EVENTPLUS_SCHEMA_CONTEXT_v1_1.md
EVENTPLUS_UI_UX_GUIDELINES.md
```

Este archivo define el alcance funcional del MVP y corrige inconsistencias detectadas entre el documento de MVP, las decisiones previas del proyecto y la estructura real de Supabase.

---

## 2. Precedencia de documentos

Cuando Codex encuentre diferencias entre documentos, debe aplicar este orden de prioridad:

```text
1. EVENTPLUS_SCHEMA_CONTEXT_v1_1.md
   Fuente de verdad para tablas, columnas, funciones, triggers, vistas e índices.

2. EVENTPLUS_MVP_SCOPE_AND_CODEX_RULES_v1_0.md
   Fuente de verdad para alcance funcional del MVP.

3. EVENTPLUS_CONTEXT.md
   Fuente de verdad para arquitectura general, roles y flujo técnico.

4. EVENTPLUS_UI_UX_GUIDELINES.md
   Fuente de verdad para diseño, usabilidad, responsividad y componentes.
```

Si hay conflicto entre UI y MVP, para el MVP prevalece este documento.

---

## 3. Resumen del MVP v1.0

La primera versión funcional de EventPlus debe permitir:

```text
Login con Google
→ Validar usuario EventPlus
→ Cargar contexto del usuario
→ Mostrar Dashboard del evento default
→ Navegar a Registro de llegadas
→ Buscar invitado
→ Confirmar llegada
→ Registrar/consultar novedad
→ Cambiar preferencias de cuenta/evento default
→ Crear/editar usuarios desde rol Administrador
→ Inactivar usuario desde rol Administrador, si se decide incluirlo en esta fase
```

El MVP asume que:

- Las cuentas ya existen en Supabase.
- Los eventos ya existen en Supabase.
- Los lugares, salones, mesas, invitaciones e invitados ya están cargados en Supabase.
- No se importará lista de invitados desde archivo en esta fase.
- No se crearán ni editarán eventos desde la app en esta fase.
- No se crearán ni editarán invitaciones desde la app en esta fase.
- No se cambiará el estado/fase del evento desde la app en esta fase.
- El foco operativo inicial es `Dashboard`, `Registro de llegadas`, `Preferencias` y administración básica de usuarios.

---

## 4. Corrección importante sobre Login

El documento de MVP menciona "usuario y contraseña", pero la decisión vigente del proyecto es:

```text
Login con Google OAuth usando Supabase Auth.
```

Por tanto, Codex NO debe implementar login con usuario/contraseña en esta fase.

El login debe usar el flujo ya probado:

```text
Flet → Supabase OAuth → Google → Supabase Auth → auth.users → trigger → evp_usr_usuario
```

Recordatorio técnico obligatorio:

```python
supabase.auth.exchange_code_for_session({"auth_code": code})
```

No usar:

```python
supabase.auth.exchange_code_for_session(code)
```

---

## 5. Flujo de login del MVP

### 5.1 Pantalla de login

Debe mostrar:

```text
EventPlus
Control de entrada a eventos
Botón: Iniciar sesión con Google
```

Estados visuales:

```text
Listo
Abriendo navegador
Esperando autenticación
Validando usuario
Acceso concedido
Acceso no autorizado
Error de conexión
```

### 5.2 Validación posterior a autenticación

Después de login exitoso en Supabase Auth, la aplicación debe:

1. Obtener `auth.users.id`.
2. Buscar el usuario en `evp_usr_usuario` por `usr_usuario_auth_uuid`.
3. Validar que `usr_estado = 'Activo'`.
4. Cargar contexto del usuario.
5. Determinar si es Master, Administrador, Operador o Consulta.
6. Validar acceso mínimo según rol.
7. Cargar cuenta/evento default si existen y son válidos.
8. Enviar al Dashboard o a Preferencias/selección si falta contexto default.

### 5.3 Mensajes de error

No usar siempre "Usuario no registrado" para todos los errores.

Mensajes sugeridos:

```text
No pudimos autenticarte con Google. Intenta nuevamente.
```

```text
Tu usuario fue autenticado, pero no está autorizado en EventPlus.
```

```text
Tu usuario existe, pero no tiene cuentas o eventos activos asignados.
```

```text
Tu usuario está inactivo o suspendido. Contacta al administrador.
```

---

## 6. Reglas de acceso por rol

### 6.1 Master

Definido por:

```text
evp_usr_usuario.usr_es_usuario_master = true
```

Reglas:

- Acceso global a todas las cuentas y eventos.
- No requiere registros en `evp_ucu_usuario_cuenta`.
- No requiere registros en `evp_uev_usuario_evento`.

### 6.2 Administrador

Definido por:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Administrador'
```

Reglas:

- Debe estar vinculado por lo menos a una cuenta.
- Para login exitoso debe tener al menos una cuenta disponible.
- Puede acceder a eventos de sus cuentas.
- No necesita registros en `evp_uev_usuario_evento`.
- Puede abrir el Drawer administrativo.
- Puede crear/editar usuarios en la cuenta/evento actual, según alcance MVP.

### 6.3 Operador

Definido por:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Operador'
```

Reglas:

- Debe estar vinculado a por lo menos una cuenta activa.
- Debe estar vinculado a por lo menos un evento activo mediante `evp_uev_usuario_evento`.
- Puede registrar llegadas cuando el evento está en fase `En_proceso`.
- No puede administrar usuarios.

### 6.4 Consulta

Definido por:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Consulta'
```

Reglas:

- Puede consultar información.
- No puede registrar llegadas.
- No puede modificar invitados.
- No puede administrar usuarios.

---

## 7. Contexto de usuario

Después del login, la aplicación debe crear un contexto de usuario disponible durante la sesión.

Función objetivo:

```python
cargar_contexto_usuario(auth_user_id)
```

Debe devolver al menos:

```text
usr_usuario_id
usr_usuario_auth_uuid
usr_nombre_usuario
usr_nombre_usuario_abrev
usr_email
usr_es_usuario_master
usr_estado
usr_cuenta_id_default
usr_evento_id_default
rol_global_calculado
cuentas_permitidas
eventos_permitidos
cuenta_actual
evento_actual
puede_registrar_llegadas
puede_administrar_usuarios
```

El contexto debe guardarse en memoria de la app, por ejemplo:

```python
page.session.set("usuario_contexto", contexto)
```

---

## 8. Flujo después del login exitoso

Después del login exitoso:

1. La app carga el contexto.
2. Si hay cuenta/evento default válido, entra al Dashboard.
3. Si no hay cuenta/evento default válido, va a Preferencias o selección inicial.
4. En todo momento debe mostrarse el evento actual en la parte superior de la pantalla.
5. La navegación principal debe estar disponible mientras la sesión esté activa.

---

## 9. Dashboard

### 9.1 Objetivo

Mostrar información y estadísticas generales del evento default/actual del usuario.

### 9.2 Datos mínimos

Debe mostrar:

```text
Estado operativo/fase del evento
Lugar y salón del evento
Cantidad de mesas del evento
Cantidad y porcentaje de mesas completas
Cantidad total de invitados
Cantidad y porcentaje de invitados con llegada confirmada
Cantidad y porcentaje de invitados con novedades
```

### 9.3 Fuente de datos sugerida

Usar vistas existentes cuando sea posible:

```text
evp_vw_evento_resumen
evp_vw_mesa_resumen
```

Si una métrica no está directamente en una vista, puede calcularse desde consultas a:

```text
evp_ivt_invitado
evp_mes_mesa
evp_eve_evento
evp_lug_lugar
evp_sal_salon
```

### 9.4 Visualización

Donde aplique:

- Tarjetas estadísticas.
- Gráfico de pastel para llegadas confirmadas vs pendientes.
- Gráfico de barras para mesas completas/pendientes.
- Indicador visual de fase del evento.

No saturar el Dashboard con demasiados gráficos en el MVP.

---

## 10. Registro de llegadas

### 10.1 Validación de fase

Al entrar a `Registro de llegadas`, la aplicación debe validar:

```text
evp_eve_evento.eve_fase_evento = 'En_proceso'
```

No confundir con `eve_estado`.

- `eve_estado` indica si el registro está Activo/Suspendido/Inactivo.
- `eve_fase_evento` indica la fase operativa: Pre_evento, En_proceso, Post_evento, Cerrado.

Si el evento no está en `En_proceso`, mostrar mensaje:

```text
El evento no está en fase de registro de llegadas. Contacta al administrador.
```

### 10.2 Búsqueda de invitado

La pantalla debe permitir buscar por nombre de invitado usando autocompletar.

Debe aprovechar:

```text
ivt_nombre_invitado
ivt_nombre_invitado_normalizado
```

La búsqueda no debe depender de mayúsculas, minúsculas o tildes exactas.

### 10.3 Al seleccionar invitado

La app debe mostrar:

- Nombre del evento.
- Mesa asignada del invitado.
- Lista completa de invitados incluidos en la misma invitación.
- Para cada invitado:
  - Número de puesto.
  - Nombre.
  - Estado de llegada.
  - Acción para confirmar llegada.
  - Estado/acción para registrar o consultar novedad.

La lista se obtiene con:

```text
ivt_cuenta_id
ivt_evento_id
ivt_invitacion_id
```

### 10.4 Confirmar llegada

Al confirmar llegada, actualizar inmediatamente `evp_ivt_invitado`.

Campos:

```text
ivt_llegada_confirmada = true
ivt_fecha_hora_conf_llegada = now()
ivt_usuario_conf_llegada = usr_usuario_id interno de EventPlus
```

Recomendación técnica:

- En MVP inicial se puede hacer update directo desde la app.
- Más adelante se recomienda RPC `evp_confirmar_llegada(p_invitado_uuid uuid)` para validar permisos y registrar auditoría en base de datos.

### 10.5 Novedades

La pantalla debe permitir registrar/consultar novedad.

Campos relevantes:

```text
ivt_tiene_novedad
ivt_descripcion_novedad
ivt_novedad_creada
ivt_novedad_creada_por
ivt_novedad_mod
ivt_novedad_mod_por
```

Reglas:

- Si se registra novedad, `ivt_tiene_novedad = true`.
- Registrar usuario y fecha/hora.
- Si se modifica una novedad, actualizar campos de modificación.

### 10.6 Estadísticas en pantalla de Registro de llegadas

Debe mostrar estadísticas resumidas relacionadas con el invitado seleccionado:

```text
Cantidad de invitados asignados a su mesa
Cantidad y porcentaje de invitados de esa mesa que han confirmado llegada
Cantidad total de invitados confirmados del evento
Porcentaje total de confirmados del evento
```

Puede apoyarse en:

```text
evp_vw_mesa_resumen
evp_vw_evento_resumen
```

---

## 11. Barra de navegación inferior

Para el MVP, la navegación principal debe estar fijada en la parte inferior de la pantalla.

Opciones:

```text
Dashboard
Registrar llegadas
Preferencias
Salir
```

Cada opción debe tener ícono intuitivo.

Aunque `EVENTPLUS_UI_UX_GUIDELINES.md` propone navegación adaptativa, para el MVP prevalece este documento:

```text
Usar barra inferior visible durante la navegación.
```

En desktop se puede mantener barra inferior para consistencia inicial. Una futura versión puede adaptar a NavigationRail.

Si el usuario no tiene cuenta/evento disponible:

```text
Solo debe estar habilitada la opción Salir.
```

---

## 12. Drawer administrativo

### 12.1 Disponibilidad

El Drawer solo está disponible para usuarios con rol:

```text
Administrador
```

Master también puede tener acceso administrativo si se decide tratarlo como superadministrador operativo.

### 12.2 Activación

En Flet puede implementarse con un botón de menú visible para Administrador.

El documento menciona deslizar desde el borde derecho, pero en Flet desktop/web puede no ser suficiente. Para MVP:

```text
Usar botón visible de menú administrativo.
```

El gesto de deslizar puede quedar como mejora posterior.

### 12.3 Opciones del Drawer

Opciones listadas:

```text
Crear/Editar evento                 No implementar todavía
Crear/Editar invitaciones           No implementar todavía
Cambiar estado del evento           No implementar todavía
Importar lista de invitados         No implementar todavía
Eliminar lista de invitados         No implementar todavía
Crear/Editar usuario                Implementar según alcance MVP
Inactivar usuario                   Implementar solo si se decide incluir en esta fase
Cerrar                              Implementar
```

---

## 13. Preferencias

### 13.1 Objetivo

Permitir cambiar cuenta y evento default.

Campos:

```text
Cuenta default
Evento default
```

Ambos deben usar listas desplegables con autocompletar.

### 13.2 Administrador

Puede seleccionar cuentas y eventos vinculados a su alcance.

El documento indica que Administrador puede seleccionar cuentas en estado:

```text
Activo, Suspendido, Inactivo
```

y eventos en estado:

```text
Activo, Inactivo
```

Ajuste recomendado:

- Para operación normal, destacar Activos.
- Permitir ver Inactivos/Suspendidos solo con advertencia visual.
- No permitir registrar llegadas si el evento no está Activo y en fase En_proceso.

### 13.3 Operador

Puede seleccionar solamente:

```text
Cuentas activas a las que está vinculado
Eventos activos a los que está vinculado
```

### 13.4 Actualización

Al guardar preferencias, actualizar:

```text
evp_usr_usuario.usr_cuenta_id_default
evp_usr_usuario.usr_evento_id_default
```

No permitir que el usuario escriba IDs manualmente.

---

## 14. Crear/Editar usuario

### 14.1 Disponibilidad

Solo para rol Administrador.

Master también puede tener acceso si se decide habilitar administración global.

### 14.2 Crear usuario

Al crear usuario:

- Crear registro en `evp_usr_usuario`.
- Estado inicial:

```text
usr_estado = 'Preregistrado'
```

- No llenar `usr_usuario_auth_uuid`.
- Vincular automáticamente a la cuenta actual en `evp_ucu_usuario_cuenta`.
- Si el rol creado es Operador o Consulta, vincular también al evento actual en `evp_uev_usuario_evento`.
- Si el rol creado es Administrador, no necesita vínculo en `evp_uev_usuario_evento`.

### 14.3 Estado y vinculación Auth

El documento dice que la aplicación cambia el estado a Activo cuando el usuario entra por primera vez.

Ajuste técnico vigente:

```text
El trigger sobre auth.users hace esta actualización.
```

La app no debe cambiar directamente `usr_estado` de Preregistrado a Activo durante login.

### 14.4 Campos editables

El formulario no debe mostrar todos los nombres técnicos como formulario principal.

Formulario principal sugerido:

```text
Nombre de usuario
Nombre abreviado
Email
Teléfono
Rol en cuenta
Acceso a evento actual, si aplica
```

Campos técnicos no editables:

```text
usr_usuario_id
usr_usuario_auth_uuid
usr_es_usuario_master
usr_cuenta_id_default
usr_evento_id_default
usr_estado
usr_creado
usr_modificado
```

Pueden mostrarse en una sección "Información técnica" colapsada o solo en modo debug/admin avanzado.

### 14.5 Invitación por email

El documento indica que al preregistrar usuario, el sistema envía un email.

Para MVP:

- Si no hay backend/servicio de correo todavía, no simular envío real.
- Mostrar mensaje: `Usuario preregistrado. Envío de invitación pendiente de configuración.`
- O generar plantilla de correo para envío manual.
- El envío automático puede implementarse luego mediante servicio externo, Edge Function, SMTP o proveedor transaccional.

---

## 15. Inactivar usuario

El documento incluye una sección funcional para inactivar usuario, pero también el Drawer dice "No implementar todavía".

Resolución para Codex:

```text
No implementarlo en el primer incremento de código salvo instrucción explícita.
```

Mantenerlo como alcance funcional documentado para MVP administrativo posterior.

Si se implementa:

- Solo Administrador/Master.
- Buscar usuario con autocompletar.
- Pedir confirmación explícita.
- Actualizar `evp_usr_usuario.usr_estado = 'Inactivo'`.
- No borrar físicamente el usuario.
- No eliminar `auth.users`.
- No eliminar relaciones históricas.

---

## 16. Funcionalidades fuera de alcance inicial

No implementar todavía:

```text
Crear/Editar evento
Crear/Editar invitaciones
Cambiar fase/estado del evento
Importar lista de invitados
Eliminar lista de invitados
Carga masiva de invitados
Administración completa de mesas
Administración completa de lugares/salones
RLS
Facturación/suscripciones
Envío automático real de emails
```

---

## 17. Pantallas del MVP y orden de desarrollo

### Incremento 1

```text
Login Google
Cargar contexto usuario
Home/Dashboard simple
Barra navegación inferior
Salir
```

### Incremento 2

```text
Preferencias cuenta/evento default
Cambio de evento actual
Validación de evento disponible
```

### Incremento 3

```text
Registro de llegadas
Búsqueda por invitado
Lista de invitados de la invitación
Confirmar llegada
Estadísticas de mesa/evento
```

### Incremento 4

```text
Registrar/consultar novedad
Actualizar indicadores visuales
```

### Incremento 5

```text
Crear/Editar usuario para Administrador
Preregistro usuario
Vinculación usuario-cuenta/evento
```

### Incremento 6 opcional

```text
Inactivar usuario
```

---

## 18. Criterios de aceptación del MVP

El MVP se considera funcional cuando:

1. El usuario inicia sesión con Google.
2. La app reconoce su usuario en `evp_usr_usuario`.
3. La app carga su contexto.
4. La app identifica su rol.
5. La app muestra evento actual en el encabezado.
6. La app muestra Dashboard con métricas básicas.
7. La app permite ir a Registro de llegadas.
8. La app valida que el evento esté en fase `En_proceso`.
9. La app permite buscar un invitado.
10. La app muestra la lista de invitados de la misma invitación.
11. La app permite confirmar llegada.
12. La app actualiza `evp_ivt_invitado`.
13. La app muestra estadísticas resumidas.
14. La app permite cambiar preferencias de cuenta/evento default.
15. La app permite salir de la sesión.
16. El Administrador puede acceder al Drawer administrativo.
17. El Administrador puede preregistrar usuarios si se implementa ese incremento.

---

## 19. Reglas visuales específicas para este MVP

Aunque la guía UI permite navegación adaptativa, para esta versión:

```text
Usar barra inferior fija como navegación principal.
```

Reglas:

- Mostrar evento actual arriba.
- Mostrar la barra inferior siempre que el usuario tenga acceso válido.
- Si no hay cuenta/evento válido, solo permitir Salir.
- Usar íconos claros.
- Evitar pantallas densas.
- Usar tarjetas para métricas.
- Usar autocompletar para búsqueda de invitados y preferencias.
- No mostrar nombres técnicos de columnas en la interfaz visible.

---

## 20. Instrucción obligatoria para Codex

Antes de modificar código, Codex debe leer:

```text
EVENTPLUS_CONTEXT.md
EVENTPLUS_SCHEMA_CONTEXT_v1_1.md
EVENTPLUS_UI_UX_GUIDELINES.md
EVENTPLUS_MVP_SCOPE_AND_CODEX_RULES_v1_0.md
```

Codex debe respetar:

- La estructura real de Supabase.
- El login con Google OAuth.
- El uso de `SUPABASE_PUBLISHABLE_KEY`.
- La separación entre usuario interno EventPlus y `auth.users.id`.
- La generación de consecutivos por triggers.
- La barra inferior fija para el MVP.
- El alcance funcional definido en este archivo.

No debe implementar funcionalidades fuera de alcance sin autorización explícita.
