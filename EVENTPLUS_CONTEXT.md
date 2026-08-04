# EVENTPLUS_CONTEXT.md

## Diseño de importación Excel (2026-08-03)

Se diseñó, sin implementar, una carga XLSX de mesas, invitaciones e invitados
para el evento activo. Las nueve columnas aprobadas son suficientes; sus códigos
son referencias externas y los IDs reales los generarán los triggers. La futura
v1 será exclusiva de FULL, Master/Administrador, evento Activo en `Pre_evento`,
sin datos previos, con preview local y una sola RPC transaccional. No se agregó
`openpyxl` ni se modificó Supabase. Véase `docs/EXCEL_IMPORT_DESIGN.md`.

## Actualización: Dashboard operativo (2026-08-03)

El Dashboard FULL consume datos reales del evento activo mediante dos consultas
filtradas, muestra ocho KPI y tres visualizaciones nativas responsive. Master,
Administrador, Operador y Consulta pueden verlo; la autorización se valida antes
de consultar. CHECKIN, autenticación, sesiones, ASGI y cookies no fueron
modificados. Detalle: `docs/DASHBOARD_MODULE.md`.

## Actualización: administración de eventos (2026-07-30)

FULL expone Administración de eventos en el menú de usuario únicamente para
Master y Administrador. El servicio filtra por la cuenta activa, no acepta
`cuenta_id` desde formularios y sincroniza `evento_actual` después de cambios.
Operador, Consulta y CHECKIN no exponen el módulo. El ciclo permitido es
`Pre_evento → En_proceso → Post_evento`; no hay reapertura. El predeterminado se
guarda solo en `evp_usr_usuario` para el usuario actual.

### Esquema autoritativo

`C:\WORKSPACE\EVENTPLUS\esquema.sql` es la fuente de verdad actual.
`eve_tipo_evento` admite `Boda`, `Cumpleaños`, `Quinceaños`, `Corporativo` y `Otro`.
Su default vigente es `Otro`, aplicado manualmente en Supabase el 2 de agosto de
2026 y validado mediante una nueva exportación completa del esquema.

## 1. Objetivo del proyecto

EventPlus es una aplicación web desarrollada en **Python + Flet + Supabase** para controlar la entrada de invitados a eventos.

La primera versión del módulo incluye:

- Autenticación de usuarios con Google OAuth usando Supabase Auth.
- Preregistro de usuarios en la tabla interna de EventPlus.
- Vinculación automática entre `auth.users.id` de Supabase y `evp_usr_usuario.usr_usuario_auth_uuid`.
- Manejo de cuentas, eventos, invitaciones, mesas e invitados.
- Confirmación de llegada de invitados.
- Base preparada para actualizaciones en tiempo real usando Supabase Realtime.
- Separación futura por roles: Master, Administrador, Operador y Consulta.

---

## 2. Stack tecnológico

La aplicación usa:

- Python
- Flet
- Supabase
- Supabase Auth
- Google OAuth
- PostgreSQL
- Supabase Realtime
- python-dotenv

Dependencias principales:

```bash
pip install flet supabase python-dotenv
```

---

## 3. Variables de entorno

La aplicación debe leer la configuración desde un archivo `.env`.

Variables esperadas:

```env
SUPABASE_URL=https://xxxxxxxxxxxxxxxxxxxx.supabase.co
SUPABASE_PUBLISHABLE_KEY=tu_publishable_key
SUPABASE_OAUTH_REDIRECT_URL=http://localhost:8765/auth/callback
```

No usar `service_role`, `secret key` ni claves privadas en código cliente.

La aplicación cliente debe usar únicamente:

```env
SUPABASE_PUBLISHABLE_KEY
```

---

## 4. Estado actual del proyecto

Ya existe una estructura completa de base de datos en Supabase.

Ya se probó exitosamente el flujo:

```text
Google OAuth → Supabase Auth → auth.users → trigger → evp_usr_usuario
```

El archivo funcional de prueba fue:

```text
app_publishable_key_v4.py
```

Ese archivo permite:

1. Abrir navegador para login con Google.
2. Autenticar al usuario con Supabase Auth.
3. Recibir callback local en `http://localhost:8765/auth/callback`.
4. Intercambiar el auth code por sesión Supabase.
5. Leer `auth.users.id`.
6. Consultar `evp_usr_usuario`.
7. Validar que el trigger actualizó `usr_usuario_auth_uuid`.

Punto técnico importante:

```python
supabase.auth.exchange_code_for_session({"auth_code": code})
```

No usar:

```python
supabase.auth.exchange_code_for_session(code)
```

porque en `supabase-py` eso genera error.

---

## 5. Configuración OAuth

En Supabase:

```text
Authentication → Providers → Google
```

Debe estar configurado Google OAuth con Client ID y Client Secret de Google Cloud.

En Google Cloud se debe usar un OAuth Client tipo:

```text
Web application
```

No usar Desktop Client.

En Google Cloud, el Authorized Redirect URI debe ser el callback de Supabase:

```text
https://TU-PROYECTO.supabase.co/auth/v1/callback
```

En Supabase, dentro de Redirect URLs, debe estar:

```text
http://localhost:8765/auth/callback
```

Este callback local es usado por la aplicación Flet de prueba.

---

## 6. Modelo de usuarios

EventPlus no usa directamente `auth.users.id` como llave primaria interna.

La tabla principal de usuarios de EventPlus es:

```text
evp_usr_usuario
```

Campos relevantes:

```text
usr_usuario_id              UUID interno de EventPlus
usr_usuario_auth_uuid       UUID de Supabase Auth / auth.users.id
usr_nombre_usuario
usr_nombre_usuario_abrev
usr_email
usr_es_usuario_master
usr_cuenta_id_default
usr_evento_id_default
usr_estado
```

Regla importante:

- `usr_usuario_id` es el identificador interno de EventPlus.
- `usr_usuario_auth_uuid` se llena cuando el usuario inicia sesión por primera vez con Google.
- El usuario puede existir como `Preregistrado` antes de tener `usr_usuario_auth_uuid`.

Estados válidos:

```text
Preregistrado
Activo
Inactivo
Suspendido
```

---

## 7. Flujo de preregistro de usuario

Antes de que un usuario inicie sesión por primera vez, debe existir un registro en:

```text
evp_usr_usuario
```

con:

```text
usr_email = email real de Google del usuario
usr_estado = 'Preregistrado'
usr_usuario_auth_uuid = NULL
```

Cuando el usuario inicia sesión con Google:

1. Supabase crea o identifica el usuario en `auth.users`.
2. Se dispara el trigger sobre `auth.users`.
3. El trigger busca en `evp_usr_usuario` por email.
4. Actualiza `usr_usuario_auth_uuid` con `auth.users.id`.
5. Cambia `usr_estado` a `Activo`.

---

## 8. Roles de usuario

EventPlus maneja estos roles:

### Master

Se define en:

```text
evp_usr_usuario.usr_es_usuario_master = true
```

Reglas:

- Tiene acceso global a todas las cuentas y todos los eventos.
- No necesita registros en `evp_ucu_usuario_cuenta`.
- No necesita registros en `evp_uev_usuario_evento`.

### Administrador

Se define en:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Administrador'
```

Reglas:

- Está vinculado a una o más cuentas.
- Tiene acceso a todos los eventos de sus cuentas.
- No necesita registros en `evp_uev_usuario_evento`.

### Operador

Se define en:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Operador'
```

Reglas:

- Está vinculado a una cuenta.
- Solo puede acceder a eventos específicos asignados en `evp_uev_usuario_evento`.
- Puede registrar llegadas.
- No debe poder hacer administración global.

### Consulta

Se define en:

```text
evp_ucu_usuario_cuenta.ucu_rol = 'Consulta'
```

Reglas:

- Es un rol de cuenta, no Master ni un estado de usuario.
- Solo accede a eventos asignados en `evp_uev_usuario_evento`, igual que
  Operador en alcance de lectura.
- Puede usar Dashboard, buscar invitados o mesas y abrir detalles.
- Es estrictamente de solo lectura: no crea, edita, elimina, confirma o
  revierte llegadas, registra imprevistos ni ejecuta servicios de escritura.

---

## 9. Tablas principales

Tablas creadas en Supabase:

```text
evp_cta_cuenta
evp_usr_usuario
evp_ucu_usuario_cuenta
evp_pai_pais
evp_lug_lugar
evp_sal_salon
evp_eve_evento
evp_uev_usuario_evento
evp_mes_mesa
evp_inv_invitacion
evp_ivt_invitado
```

`evp_lug_lugar` y `evp_sal_salon` disponen de administración en modo FULL para
Master y Administrador: alta, edición y cambio de estado sin DELETE físico. El
servicio filtra por la cuenta activa autorizada y deja los IDs relativos a los
triggers. Operador, Consulta y CHECKIN no exponen este módulo.

---

## 10. Consecutivos relativos

La base de datos tiene triggers para generar automáticamente consecutivos relativos.

La aplicación Flet no debe calcular manualmente estos IDs.

No calcular en Python usando:

```text
max(id) + 1
```

Los triggers generan:

```text
lug_lugar_id           por cuenta
sal_salon_id           por cuenta/lugar
eve_evento_id          por cuenta
mes_mesa_id            por cuenta/evento
inv_invitacion_id      por cuenta/evento
ivt_invitado_id        por cuenta/evento/invitación
```

Cuando se inserta un registro, la aplicación debe omitir esos campos y dejar que Supabase los asigne.

---

## 11. Tabla de invitados

Tabla:

```text
evp_ivt_invitado
```

Campos importantes:

```text
ivt_cuenta_id
ivt_evento_id
ivt_invitacion_id
ivt_invitado_id
ivt_invitado_uuid
ivt_nombre_invitado
ivt_nombre_invitado_normalizado
ivt_es_invitado_principal
ivt_es_invitado_imprevisto
ivt_email
ivt_telefono
ivt_mesa_id
ivt_puesto_id
ivt_llegada_confirmada
ivt_fecha_hora_conf_llegada
ivt_usuario_conf_llegada
ivt_tiene_novedad
ivt_descripcion_novedad
ivt_estado
```

`ivt_invitado_uuid` existe como identificador técnico para facilitar el manejo desde Flet.

La llave primaria de negocio sigue siendo compuesta:

```text
ivt_cuenta_id
ivt_evento_id
ivt_invitacion_id
ivt_invitado_id
```

---

## 12. Realtime

La tabla principal para realtime en la primera versión es:

```text
evp_ivt_invitado
```

El primer objetivo realtime será actualizar la lista de invitados cuando otro usuario confirme una llegada.

Campos que cambian al confirmar llegada:

```text
ivt_llegada_confirmada = true
ivt_fecha_hora_conf_llegada = now()
ivt_usuario_conf_llegada = usuario interno EventPlus
```

---

## 13. Reglas de negocio iniciales

Fases del evento:

```text
Pre_evento
En_proceso
Post_evento
Cerrado
```

Reglas esperadas:

- En `Pre_evento` se puede preparar información.
- En `En_proceso` se pueden confirmar llegadas.
- En `Post_evento` debe ser principalmente consulta.
- En `Cerrado` no se deben permitir modificaciones operativas.

Reglas de invitados:

- No se deben permitir invitados activos duplicados dentro del mismo evento usando el nombre normalizado.
- Los invitados imprevistos deben marcarse con `ivt_es_invitado_imprevisto = true`.
- La confirmación de llegada debe registrar usuario y fecha/hora.

---

## 14. Estructura objetivo del código

La aplicación debe refactorizarse gradualmente hacia esta estructura:

```text
EVENTPLUS/
│
├── app.py
├── db.py
├── config.py
├── EVENTPLUS_CONTEXT.md
├── .env
│
├── services/
│   ├── auth_service.py
│   ├── usuario_service.py
│   ├── evento_service.py
│   └── invitado_service.py
│
├── views/
│   ├── login_view.py
│   ├── home_view.py
│   ├── evento_select_view.py
│   └── invitados_view.py
```

---

## 15. Reglas para Codex

Cuando Codex modifique el proyecto debe respetar estas reglas:

1. No cambiar nombres de tablas ni columnas sin autorización.
2. No usar `service_role` ni claves secretas en código cliente.
3. Usar `SUPABASE_PUBLISHABLE_KEY`.
4. Mantener el callback OAuth local:

```text
http://localhost:8765/auth/callback
```

5. Mantener el flujo de Supabase OAuth, no reemplazarlo por OAuth directo de Flet.
6. Mantener:

```python
exchange_code_for_session({"auth_code": code})
```

7. No activar RLS todavía.
8. No modificar el modelo de base de datos sin autorización.
9. No calcular consecutivos relativos desde Python.
10. Mantener la aplicación ejecutable con:

```bash
python app.py
```

---

## 16. Próximo objetivo técnico

El próximo objetivo es convertir la prueba funcional de login en el módulo base de autenticación.

Flujo esperado:

```text
Login exitoso
→ cargar usuario EventPlus
→ validar estado Activo
→ determinar si es Master, Administrador, Operador o Consulta
→ cargar cuentas disponibles
→ cargar eventos disponibles
→ mostrar Home simple
```

La función clave a crear será:

```python
cargar_contexto_usuario(auth_user_id)
```

Debe devolver información como:

```text
usr_usuario_id
usr_email
usr_nombre_usuario
usr_es_usuario_master
usr_estado
cuentas permitidas
eventos permitidos
cuenta default
evento default
rol por cuenta
```

---

## 17. Criterio de avance

No avanzar a pantallas de invitados hasta que funcione correctamente:

```text
Login Google
→ usuario EventPlus activo
→ contexto de usuario cargado
→ cuenta/evento disponible
```

Después de eso, el siguiente módulo será:

```text
Pantalla de invitados
→ búsqueda de invitado
→ confirmar llegada
→ actualización realtime
```
