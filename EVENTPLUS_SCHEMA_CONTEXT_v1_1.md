# EVENTPLUS_SCHEMA_CONTEXT_v1_1.md

## 1. Propósito de este archivo

Este archivo complementa `EVENTPLUS_CONTEXT.md`.

Debe ser leído por Codex antes de modificar código relacionado con Supabase, consultas, servicios, pantallas o reglas de negocio.

La fuente de referencia es el script SQL más reciente de EventPlus v1.1.

Codex debe tratar esta estructura como la estructura real vigente de la base de datos, salvo que Rafael indique explícitamente que cambió.

---

## 2. Advertencias importantes para Codex

1. No cambiar nombres de tablas ni columnas sin autorización.
2. No calcular consecutivos relativos desde Python/Flet.
3. No usar `service_role`, `secret key` ni claves privadas en la app cliente.
4. Usar `SUPABASE_PUBLISHABLE_KEY`.
5. No activar RLS todavía.
6. No crear nuevas tablas sin autorización.
7. No asumir que `auth.users.id` es la llave primaria interna de EventPlus.
8. La llave interna de usuario es `evp_usr_usuario.usr_usuario_id`.
9. El vínculo con Supabase Auth se hace mediante `evp_usr_usuario.usr_usuario_auth_uuid`.
10. Para OAuth en supabase-py usar:

```python
supabase.auth.exchange_code_for_session({"auth_code": code})
```

---

## 3. Extensiones y funciones base

El script usa:

```sql
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;
```

La función de normalización es:

```sql
public.evp_normalizar_texto(p_texto text)
```

Objetivo:

- Convertir texto a minúscula.
- Quitar espacios sobrantes.
- Quitar tildes usando `extensions.unaccent`.
- Ayudar a evitar duplicados de invitados por variaciones de mayúsculas/tildes/espacios.

Nota técnica importante:

El DDL usa `extensions.gen_random_uuid()` en columnas UUID. Si se recrea la base desde cero, asegurarse de que `pgcrypto` esté disponible en el esquema `extensions`, o agregar explícitamente:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
```

---

## 4. Tablas principales

### 4.1 `evp_cta_cuenta`

Objetivo: representa una cuenta/cliente dentro de EventPlus.

Columnas principales:

```text
cta_cuenta_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY
cta_nombre_cuenta varchar(100) NOT NULL
cta_nombre_cuenta_abrev varchar(15)
cta_nombre_contacto varchar(80) NOT NULL
cta_telefono_contacto varchar(20)
cta_email_contacto varchar(254)
cta_tipo_suscripcion varchar(15) NOT NULL DEFAULT 'Demo'
cta_fecha_venc_suscripcion date NOT NULL
cta_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Valores válidos:

```text
cta_tipo_suscripcion: Premium, Estandar, Demo
cta_estado: Activo, Inactivo, Suspendido
```

Regla:

- No enviar `cta_cuenta_id` desde Python; PostgreSQL lo genera.

---

### 4.2 `evp_usr_usuario`

Objetivo: usuario interno de EventPlus.

Columnas principales:

```text
usr_usuario_id uuid PRIMARY KEY DEFAULT extensions.gen_random_uuid()
usr_nombre_usuario varchar(50) NOT NULL
usr_nombre_usuario_abrev varchar(12) NOT NULL
usr_usuario_auth_uuid uuid UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL
usr_es_usuario_master boolean NOT NULL DEFAULT false
usr_email varchar(254) NOT NULL
usr_cuenta_id_default integer REFERENCES evp_cta_cuenta(cta_cuenta_id)
usr_evento_id_default integer
usr_telefono varchar(20)
usr_creado timestamptz NOT NULL DEFAULT now()
usr_modificado timestamptz
usr_estado varchar(15) NOT NULL DEFAULT 'Preregistrado'
```

Valores válidos:

```text
usr_estado: Preregistrado, Activo, Inactivo, Suspendido
```

Reglas:

- `usr_usuario_id` es el ID interno de EventPlus.
- `usr_usuario_auth_uuid` se llena cuando el usuario inicia sesión por primera vez con Google/Supabase Auth.
- Un usuario puede estar preregistrado antes de tener `usr_usuario_auth_uuid`.
- Master se define con `usr_es_usuario_master = true`.

---

### 4.3 `evp_ucu_usuario_cuenta`

Objetivo: vincula usuarios con cuentas.

Columnas principales:

```text
ucu_cuenta_id integer NOT NULL
ucu_usuario_id uuid NOT NULL
ucu_rol varchar(20) NOT NULL
ucu_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
ucu_cuenta_id, ucu_usuario_id
```

Valores válidos:

```text
ucu_rol: Administrador, Operador, Consulta
ucu_estado: Activo, Suspendido, Inactivo
```

Reglas:

- Administrador tiene acceso a todos los eventos de sus cuentas.
- Operador debe estar vinculado además a eventos en `evp_uev_usuario_evento`.
- Consulta requiere asignaciones activas en `evp_uev_usuario_evento` y puede
  ver, pero no modificar, los eventos asignados.

---

### 4.4 `evp_pai_pais`

Objetivo: catálogo de países.

Columnas principales:

```text
pai_pais_id varchar(2) PRIMARY KEY
pai_nombre_pais varchar(50) NOT NULL
```

---

### 4.5 `evp_lug_lugar`

Objetivo: lugares de evento por cuenta.

Columnas principales:

```text
lug_cuenta_id integer NOT NULL
lug_lugar_id integer NOT NULL
lug_nombre_lugar varchar(50) NOT NULL
lug_direccion varchar(150)
lug_ciudad varchar(50)
lug_pais_id varchar(2)
lug_tipo_lugar varchar(20) NOT NULL DEFAULT 'Otro'
lug_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
lug_cuenta_id, lug_lugar_id
```

Valores válidos:

```text
lug_tipo_lugar: Hotel, Sala de eventos, Otro
lug_estado: Activo, Suspendido, Inactivo
```

Regla:

- No enviar `lug_lugar_id` desde Python; trigger lo genera por cuenta.

---

### 4.6 `evp_sal_salon`

Objetivo: salones dentro de un lugar.

Columnas principales:

```text
sal_cuenta_id integer NOT NULL
sal_lugar_id integer NOT NULL
sal_salon_id integer NOT NULL
sal_nombre_salon varchar(60) NOT NULL
sal_ubicacion varchar(100)
sal_cant_max_mesas integer
sal_cant_max_invitados integer
sal_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
sal_cuenta_id, sal_lugar_id, sal_salon_id
```

Valores válidos:

```text
sal_estado: Activo, Suspendido, Inactivo
```

Regla:

- No enviar `sal_salon_id` desde Python; trigger lo genera por cuenta/lugar.

---

### 4.7 `evp_eve_evento`

Objetivo: eventos creados por cuenta.

Columnas principales:

```text
eve_cuenta_id integer NOT NULL
eve_evento_id integer NOT NULL
eve_nombre_evento varchar(50) NOT NULL
eve_nombre_evento_abrev varchar(20)
eve_fase_evento varchar(20) NOT NULL DEFAULT 'Pre_evento'
eve_tipo_evento varchar(1) NOT NULL DEFAULT 'O'
eve_lugar_id integer NOT NULL
eve_salon_id integer NOT NULL
eve_cant_mesas integer
eve_fecha_hora_inicio timestamptz
eve_fecha_hora_fin timestamptz
eve_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
eve_cuenta_id, eve_evento_id
```

Valores válidos:

```text
eve_fase_evento: Pre_evento, En_proceso, Post_evento, Cerrado
eve_tipo_evento: B, Q, A, C, O
eve_estado: Activo, Suspendido, Inactivo
```

Reglas:

- No enviar `eve_evento_id` desde Python; trigger lo genera por cuenta.
- `eve_fecha_hora_fin` debe ser mayor que `eve_fecha_hora_inicio` cuando ambas existan.

---

### 4.8 `evp_uev_usuario_evento`

Objetivo: asigna usuarios Operador/Consulta a eventos específicos.

Columnas principales:

```text
uev_cuenta_id integer NOT NULL
uev_evento_id integer NOT NULL
uev_usuario_id uuid NOT NULL
uev_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
uev_cuenta_id, uev_evento_id, uev_usuario_id
```

Valores válidos:

```text
uev_estado: Activo, Suspendido, Inactivo
```

Reglas:

- Un Operador o Consulta debe existir primero en `evp_ucu_usuario_cuenta`.
- Administrador no necesita registros en esta tabla.
- Master no necesita registros en esta tabla.

---

### 4.9 `evp_mes_mesa`

Objetivo: mesas del evento.

Columnas principales:

```text
mes_cuenta_id integer NOT NULL
mes_evento_id integer NOT NULL
mes_mesa_id integer NOT NULL
mes_nombre_mesa varchar(30) NOT NULL
mes_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
mes_cuenta_id, mes_evento_id, mes_mesa_id
```

Valores válidos:

```text
mes_estado: Activo, Suspendido, Inactivo
```

Regla:

- No enviar `mes_mesa_id` desde Python; trigger lo genera por cuenta/evento.

---

### 4.10 `evp_inv_invitacion`

Objetivo: invitaciones de un evento.

Columnas principales:

```text
inv_cuenta_id integer NOT NULL
inv_evento_id integer NOT NULL
inv_invitacion_id integer NOT NULL
inv_cod_abrev_invitacion char(3)
inv_token_qr_invitacion varchar(100) UNIQUE
inv_destinatario_invitacion varchar(100) NOT NULL
inv_cant_puestos_reservados integer NOT NULL DEFAULT 0
inv_fecha_stdate_enviado date
inv_conf_stdate_recibido boolean NOT NULL DEFAULT false
inv_fecha_invitacion_enviada date
inv_conf_invitacion_recibida boolean NOT NULL DEFAULT false
inv_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
inv_cuenta_id, inv_evento_id, inv_invitacion_id
```

Valores válidos:

```text
inv_estado: Activo, Suspendido, Inactivo
```

Reglas:

- No enviar `inv_invitacion_id` desde Python; trigger lo genera por cuenta/evento.
- `inv_cod_abrev_invitacion` debe ser único por evento cuando no sea NULL.

---

### 4.11 `evp_ivt_invitado`

Objetivo: invitados registrados dentro de una invitación.

Columnas principales:

```text
ivt_cuenta_id integer NOT NULL
ivt_evento_id integer NOT NULL
ivt_invitacion_id integer NOT NULL
ivt_invitado_id integer NOT NULL
ivt_invitado_uuid uuid NOT NULL DEFAULT extensions.gen_random_uuid()
ivt_nombre_invitado varchar(80) NOT NULL
ivt_nombre_invitado_normalizado text GENERATED ALWAYS AS (public.evp_normalizar_texto(ivt_nombre_invitado)) STORED
ivt_es_invitado_principal boolean NOT NULL DEFAULT false
ivt_es_invitado_imprevisto boolean NOT NULL DEFAULT false
ivt_email varchar(254)
ivt_telefono varchar(20)
ivt_mesa_id integer
ivt_puesto_id integer
ivt_llegada_confirmada boolean NOT NULL DEFAULT false
ivt_fecha_hora_conf_llegada timestamptz
ivt_usuario_conf_llegada uuid
ivt_tiene_novedad boolean NOT NULL DEFAULT false
ivt_descripcion_novedad varchar(200)
ivt_novedad_creada timestamptz
ivt_novedad_creada_por uuid
ivt_novedad_mod timestamptz
ivt_novedad_mod_por uuid
ivt_invitado_creado timestamptz NOT NULL DEFAULT now()
ivt_invitado_creado_por uuid
ivt_invitado_mod timestamptz
ivt_invitado_mod_por uuid
ivt_estado varchar(15) NOT NULL DEFAULT 'Activo'
```

Llave primaria:

```text
ivt_cuenta_id, ivt_evento_id, ivt_invitacion_id, ivt_invitado_id
```

Valores válidos:

```text
ivt_estado: Activo, Suspendido, Inactivo
```

Reglas:

- No enviar `ivt_invitado_id` desde Python; trigger lo genera por cuenta/evento/invitación.
- `ivt_invitado_uuid` puede usarse en Flet como identificador técnico de fila.
- No permitir duplicados activos por `ivt_nombre_invitado_normalizado` dentro del mismo evento.
- Solo un invitado principal activo por invitación.
- Si `ivt_llegada_confirmada = true`, debe existir `ivt_fecha_hora_conf_llegada`.

---

## 5. Funciones creadas

Funciones principales:

```text
evp_normalizar_texto(p_texto text)
evp_fn_set_lugar_id()
evp_fn_set_salon_id()
evp_fn_set_evento_id()
evp_fn_set_mesa_id()
evp_fn_set_invitacion_id()
evp_fn_set_invitado_id()
evp_fn_touch_usuario()
evp_fn_touch_invitado()
evp_fn_set_usuario_cuenta_default()
evp_fn_set_usuario_evento_default()
evp_fn_vincular_usuario_auth()
evp_usuario_id_actual()
evp_es_usuario_master()
evp_tiene_acceso_cuenta(p_cuenta_id integer)
evp_puede_ver_evento(p_cuenta_id integer, p_evento_id integer)
```

Funciones útiles para la app:

### `evp_usuario_id_actual()`

Devuelve el `usr_usuario_id` interno de EventPlus correspondiente al usuario autenticado por Supabase Auth.

Usa:

```text
auth.uid() → evp_usr_usuario.usr_usuario_auth_uuid → evp_usr_usuario.usr_usuario_id
```

### `evp_es_usuario_master()`

Devuelve `true` si el usuario autenticado tiene `usr_es_usuario_master = true` y está activo.

### `evp_tiene_acceso_cuenta(p_cuenta_id integer)`

Devuelve `true` si el usuario autenticado es Master o tiene acceso activo a la cuenta.

### `evp_puede_ver_evento(p_cuenta_id integer, p_evento_id integer)`

Devuelve `true` si el usuario autenticado puede ver el evento.

Regla implementada:

- Master puede ver todo.
- Administrador puede ver todos los eventos de sus cuentas.
- Operador y Consulta solo pueden ver eventos asignados en
  `evp_uev_usuario_evento`.
- Operador puede ver eventos asignados en `evp_uev_usuario_evento`.

---

## 6. Triggers creados

Triggers principales:

```text
trg_evp_lug_set_id       → evp_lug_lugar       → evp_fn_set_lugar_id()
trg_evp_sal_set_id       → evp_sal_salon       → evp_fn_set_salon_id()
trg_evp_eve_set_id       → evp_eve_evento      → evp_fn_set_evento_id()
trg_evp_mes_set_id       → evp_mes_mesa        → evp_fn_set_mesa_id()
trg_evp_inv_set_id       → evp_inv_invitacion  → evp_fn_set_invitacion_id()
trg_evp_ivt_set_id       → evp_ivt_invitado    → evp_fn_set_invitado_id()
trg_evp_usr_touch        → evp_usr_usuario     → evp_fn_touch_usuario()
trg_evp_ivt_touch        → evp_ivt_invitado    → evp_fn_touch_invitado()
trg_evp_ucu_set_default  → evp_ucu_usuario_cuenta → evp_fn_set_usuario_cuenta_default()
trg_evp_uev_set_default  → evp_uev_usuario_evento → evp_fn_set_usuario_evento_default()
trg_evp_vincular_usuario_auth → auth.users     → evp_fn_vincular_usuario_auth()
```

Regla para Codex:

- Al insertar registros con consecutivos relativos, omitir el ID relativo y dejar que el trigger lo asigne.

---

## 7. Vistas creadas

### `evp_vw_mesa_resumen`

Objetivo:

- Mostrar resumen por mesa.

Columnas relevantes:

```text
mes_cuenta_id
mes_evento_id
mes_mesa_id
mes_nombre_mesa
cant_puestos_reservados
cant_puestos_confirmados
cant_puestos_pendientes
```

Uso esperado:

- Pantallas de resumen de mesas.
- Estadísticas en evento.

### `evp_vw_evento_resumen`

Objetivo:

- Mostrar resumen general del evento.

Columnas relevantes:

```text
eve_cuenta_id
eve_evento_id
eve_nombre_evento
eve_fase_evento
eve_fecha_hora_inicio
eve_fecha_hora_fin
total_puestos_reservados
total_invitados_registrados
total_llegadas_confirmadas
total_pendientes_llegada
total_invitados_imprevistos
```

Uso esperado:

- Home del evento.
- Dashboard básico.
- Métricas en tiempo real.

---

## 8. Índices relevantes

Índices únicos/funcionales creados:

```text
ux_evp_usr_email_norm
ux_evp_inv_cod_abrev_evento
ux_evp_ivt_nombre_evento_activo
ux_evp_ivt_principal_invitacion
```

Reglas:

- `ux_evp_usr_email_norm`: evita duplicados por email normalizado.
- `ux_evp_inv_cod_abrev_evento`: evita códigos abreviados duplicados dentro del evento.
- `ux_evp_ivt_nombre_evento_activo`: evita invitados activos duplicados por nombre normalizado dentro del evento.
- `ux_evp_ivt_principal_invitacion`: permite solo un invitado principal activo por invitación.

---

## 9. Realtime

La tabla habilitada para realtime en la primera versión es:

```text
evp_ivt_invitado
```

La primera funcionalidad realtime será:

```text
Cuando un usuario confirme llegada, otras pantallas abiertas deben actualizar la lista/resumen.
```

Campos importantes para realtime:

```text
ivt_llegada_confirmada
ivt_fecha_hora_conf_llegada
ivt_usuario_conf_llegada
ivt_tiene_novedad
ivt_descripcion_novedad
ivt_estado
```

---

## 10. Consultas que Codex puede usar como referencia

### Buscar usuario EventPlus por auth UUID

```python
response = (
    supabase
    .table("evp_usr_usuario")
    .select(
        "usr_usuario_id,"
        "usr_nombre_usuario,"
        "usr_nombre_usuario_abrev,"
        "usr_email,"
        "usr_usuario_auth_uuid,"
        "usr_es_usuario_master,"
        "usr_cuenta_id_default,"
        "usr_evento_id_default,"
        "usr_estado"
    )
    .eq("usr_usuario_auth_uuid", auth_user_id)
    .limit(1)
    .execute()
)
```

### Consultar cuentas del usuario no Master

```python
response = (
    supabase
    .table("evp_ucu_usuario_cuenta")
    .select(
        "ucu_cuenta_id,"
        "ucu_rol,"
        "ucu_estado,"
        "evp_cta_cuenta:ucu_cuenta_id("
        "cta_nombre_cuenta,"
        "cta_nombre_cuenta_abrev,"
        "cta_estado"
        ")"
    )
    .eq("ucu_usuario_id", usr_usuario_id)
    .eq("ucu_estado", "Activo")
    .execute()
)
```

### Consultar eventos por cuenta

```python
response = (
    supabase
    .table("evp_eve_evento")
    .select("*")
    .eq("eve_cuenta_id", cuenta_id)
    .eq("eve_estado", "Activo")
    .order("eve_evento_id")
    .execute()
)
```

### Consultar invitados de un evento

```python
response = (
    supabase
    .table("evp_ivt_invitado")
    .select("*")
    .eq("ivt_cuenta_id", cuenta_id)
    .eq("ivt_evento_id", evento_id)
    .eq("ivt_estado", "Activo")
    .order("ivt_nombre_invitado")
    .execute()
)
```

### Confirmar llegada de invitado

```python
response = (
    supabase
    .table("evp_ivt_invitado")
    .update({
        "ivt_llegada_confirmada": True,
        "ivt_fecha_hora_conf_llegada": "now()",
        "ivt_usuario_conf_llegada": usr_usuario_id,
    })
    .eq("ivt_cuenta_id", cuenta_id)
    .eq("ivt_evento_id", evento_id)
    .eq("ivt_invitado_uuid", invitado_uuid)
    .execute()
)
```

Nota: si `now()` no funciona directamente desde update cliente, crear una función RPC para confirmar llegada, porque es más seguro y consistente.

---

## 11. Recomendación pendiente

Para la confirmación de llegada, se recomienda crear más adelante una función RPC como:

```text
evp_confirmar_llegada(
    p_invitado_uuid uuid
)
```

La función debería:

1. Identificar al usuario actual con `auth.uid()`.
2. Convertirlo a `usr_usuario_id` con `evp_usuario_id_actual()`.
3. Validar permisos.
4. Actualizar `ivt_llegada_confirmada`.
5. Registrar fecha/hora y usuario.
6. Devolver el registro actualizado.

Esto evitará que la app cliente manipule campos sensibles directamente.

---

## 12. Estado de seguridad

RLS todavía no está activado en esta fase.

No activar RLS hasta que:

1. Funcione login.
2. Funcione `cargar_contexto_usuario`.
3. Funcione selección de cuenta/evento.
4. Funcione consulta de invitados.
5. Funcione confirmación de llegada.
6. Estén definidas las políticas por Master, Administrador, Operador y Consulta.
