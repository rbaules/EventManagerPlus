# Diseño técnico de importación Excel de EventPlus

Estado: **7C preparada; migración RPC todavía no aplicada**. Fecha: 4 de agosto de 2026.

La implementación 7B usa `openpyxl==3.1.5`, acepta las nueve columnas en
cualquier orden (sin faltantes, extras ni duplicadas), valida localmente y no
escribe datos. La importación definitiva y su RPC continúan fuera de alcance.

Este documento define la futura importación de mesas, invitaciones e invitados
para el evento activo en FULL. No autoriza escrituras directas, cambios de
esquema, SQL remoto ni activación de RLS. La fuente autoritativa revisada
completamente es `C:\WORKSPACE\EVENTPLUS\esquema.sql` (1,098 líneas).

## 1. Decisiones ejecutivas

- Las nueve columnas aprobadas son suficientes. No se añade cuenta, evento ni
  ningún ID interno.
- `Código de invitación`, `Orden del invitado` y `Mesa ID` son referencias
  externas del archivo y nunca se insertan como PK.
- Los IDs internos se omiten en los INSERT para que los triggers vigentes los
  generen dentro de una única transacción.
- Primera versión: solo FULL, roles Master y Administrador, evento Activo en
  `Pre_evento`, y evento completamente vacío de mesas, invitaciones e invitados.
- La vista previa es local y no escribe. La confirmación futura llamará una sola
  RPC atómica; Python no hará secuencias de INSERT individuales.
- No se acepta `.xls`, `.xlsm`, macros, fórmulas sin valor calculado ni archivos
  que excedan los límites configurados.

## 2. Inventario exacto del esquema real

### 2.1 `public.evp_inv_invitacion`

| Columna | Tipo | Nulabilidad / default | Uso en importación |
|---|---|---|---|
| `inv_cuenta_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `inv_evento_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `inv_invitacion_id` | `integer` | NOT NULL | Omitida; trigger la genera |
| `inv_cod_abrev_invitacion` | `character(3)` | NULL | NULL; el código Excel no se copia aquí |
| `inv_token_qr_invitacion` | `varchar(100)` | NULL | NULL; fuera del alcance |
| `inv_destinatario_invitacion` | `varchar(100)` | NOT NULL | “Destinatario de la invitación” |
| `inv_cant_puestos_reservados` | `integer` | NOT NULL, default `0` | Conteo de filas del grupo |
| `inv_fecha_stdate_enviado` | `date` | NULL | NULL |
| `inv_conf_stdate_recibido` | `boolean` | NOT NULL, default `false` | Default |
| `inv_fecha_invitacion_enviada` | `date` | NULL | NULL |
| `inv_conf_invitacion_recibida` | `boolean` | NOT NULL, default `false` | Default |
| `inv_estado` | `varchar(15)` | NOT NULL, default `Activo` | `Activo` |

PK compuesta: (`inv_cuenta_id`, `inv_evento_id`, `inv_invitacion_id`). FK
`fk_inv_evento`: cuenta/evento → `evp_eve_evento`.

Restricciones:

- `chk_inv_cant_puestos`: puestos reservados ≥ 0.
- `chk_inv_estado`: `Activo`, `Suspendido` o `Inactivo`.
- UNIQUE global de `inv_token_qr_invitacion` cuando no es NULL.
- Índice único parcial `ux_evp_inv_cod_abrev_evento` sobre cuenta, evento y
  código abreviado cuando este no es NULL y el estado no es `Inactivo`.

Trigger `trg_evp_inv_set_id`, BEFORE INSERT, ejecuta
`evp_fn_set_invitacion_id()`: si el ID llega NULL, toma un advisory lock por
cuenta/evento y asigna `MAX(inv_invitacion_id) + 1` dentro de ese evento.
La tabla no contiene columnas generales de creación/modificación.

### 2.2 `public.evp_ivt_invitado`

| Columna | Tipo | Nulabilidad / default | Uso en importación |
|---|---|---|---|
| `ivt_cuenta_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `ivt_evento_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `ivt_invitacion_id` | `integer` | NOT NULL | Resultado del mapa de invitaciones |
| `ivt_invitado_id` | `integer` | NOT NULL | Omitida; trigger la genera |
| `ivt_invitado_uuid` | `uuid` | NOT NULL, `gen_random_uuid()` | Default |
| `ivt_nombre_invitado` | `varchar(80)` | NOT NULL | “Nombre del invitado” |
| `ivt_nombre_invitado_normalizado` | `text` | GENERATED STORED | No se envía |
| `ivt_es_invitado_principal` | `boolean` | NOT NULL, default `false` | “Es invitado principal?” normalizado |
| `ivt_es_invitado_imprevisto` | `boolean` | NOT NULL, default `false` | Siempre `false` |
| `ivt_email` | `varchar(254)` | NULL | Columna Email |
| `ivt_telefono` | `varchar(20)` | NULL | Columna Teléfono, siempre texto |
| `ivt_mesa_id` | `integer` | NULL | Resultado del mapa de mesas |
| `ivt_puesto_id` | `integer` | NULL | NULL; Orden no se copia aquí |
| `ivt_llegada_confirmada` | `boolean` | NOT NULL, default `false` | `false` |
| `ivt_fecha_hora_conf_llegada` | `timestamptz` | NULL | NULL |
| `ivt_usuario_conf_llegada` | `uuid` | NULL | NULL; FK a usuario |
| `ivt_tiene_novedad` | `boolean` | NOT NULL, default `false` | `false` |
| `ivt_descripcion_novedad` | `varchar(200)` | NULL | NULL |
| `ivt_novedad_creada` / `ivt_novedad_mod` | `timestamptz` | NULL | NULL |
| `ivt_novedad_creada_por` / `ivt_novedad_mod_por` | `uuid` | NULL | NULL; FK a usuario |
| `ivt_invitado_creado` | `timestamptz` | NOT NULL, default `now()` | Default |
| `ivt_invitado_creado_por` | `uuid` | NULL | Usuario actual de la RPC |
| `ivt_invitado_mod` | `timestamptz` | NULL | NULL |
| `ivt_invitado_mod_por` | `uuid` | NULL | NULL; FK a usuario |
| `ivt_estado` | `varchar(15)` | NOT NULL, default `Activo` | `Activo` |

PK compuesta: cuenta, evento, invitación e invitado. UNIQUE adicional:
`ivt_invitado_uuid`. FK: invitación compuesta; mesa compuesta y anulable; cinco
campos de usuario hacia `evp_usr_usuario` (creación, modificación, confirmación
de llegada y creación/modificación de novedad).

Restricciones e índices:

- Estado: `Activo`, `Suspendido` o `Inactivo`.
- Llegada confirmada exige timestamp; una fila nueva usa `false` y NULL.
- `ivt_puesto_id` debe ser NULL o mayor que cero.
- `ux_evp_ivt_nombre_evento_activo` hace único el nombre normalizado en todo el
  evento para filas no inactivas, no solo dentro de una invitación.
- `ux_evp_ivt_principal_invitacion` permite como máximo un principal no inactivo
  por invitación. El esquema no obliga a que exista uno.

`evp_normalizar_texto()` aplica `coalesce`, trim, `unaccent`, minúsculas y
colapsa espacios. `ivt_nombre_invitado_normalizado` usa exactamente esa función.
`trg_evp_ivt_set_id` genera `MAX + 1` por cuenta/evento/invitación bajo advisory
lock. `trg_evp_ivt_touch` fija `ivt_invitado_mod = now()` en UPDATE.

### 2.3 `public.evp_mes_mesa`

| Columna | Tipo | Nulabilidad / default | Uso en importación |
|---|---|---|---|
| `mes_cuenta_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `mes_evento_id` | `integer` | NOT NULL | Derivada del evento autorizado |
| `mes_mesa_id` | `integer` | NOT NULL | Omitida; trigger la genera |
| `mes_nombre_mesa` | `varchar(30)` | NOT NULL | “Nombre de mesa” |
| `mes_estado` | `varchar(15)` | NOT NULL, default `Activo` | `Activo` |

PK: cuenta/evento/mesa. FK `fk_mes_evento`: cuenta/evento → evento. CHECK de
estado: `Activo`, `Suspendido` o `Inactivo`. No hay UNIQUE para nombre, columna
de capacidad ni auditoría. `trg_evp_mes_set_id` genera `MAX + 1` por
cuenta/evento bajo advisory lock.

La FK de invitados garantiza que una mesa asignada pertenezca a la misma cuenta
y evento. `evp_vw_mesa_resumen` depende de mesas e invitados; la vista de evento
resume puestos e invitados. Ninguna vista es necesaria para insertar.

## 3. Suficiencia y derivación de la plantilla

Las nueve columnas se conservan sin cambios:

| Columna Excel | Obligatoria | Destino / interpretación |
|---|---:|---|
| Código de invitación | Sí | Clave externa temporal para agrupar |
| Destinatario de la invitación | Sí | `inv_destinatario_invitacion` |
| Orden del invitado | Sí | Orden lógico positivo; no se persiste |
| Nombre del invitado | Sí | `ivt_nombre_invitado` |
| Teléfono del invitado | No | `ivt_telefono`, texto ≤ 20 |
| Email del invitado | No | `ivt_email`, texto ≤ 254 |
| Es invitado principal? | Sí | Booleano normalizado |
| Mesa ID | No | Código externo temporal de mesa |
| Nombre de mesa | Condicional | Obligatorio cuando existe Mesa ID |

Campos derivados de contexto: cuenta, evento y usuario creador. Campos derivados
del archivo: puestos reservados = número de invitados del código. Estados:
`Activo`. Invitado planificado: `ivt_es_invitado_imprevisto = false`. Llegada y
novedad comienzan en `false`, con detalles NULL. UUID y timestamps usan defaults.

`inv_cod_abrev_invitacion` queda NULL: es `char(3)` y no existe evidencia de que
el código externo cumpla esa semántica. QR, fechas de envío y confirmaciones no
son requeridos. Mesa no tiene capacidad obligatoria ni opcional en el esquema.

## 4. Estrategia de identificadores

Durante preview se construyen mapas en memoria:

```text
external_invitation_code -> grupo validado -> inv_invitacion_id retornado
external_table_code      -> mesa validada  -> mes_mesa_id retornado
(invitation_code, guest_order) -> fila validada -> ivt_invitado_id retornado
```

Los códigos externos se normalizan como texto con trim, sin conversión numérica,
para conservar ceros iniciales. Se limita inicialmente a 50 caracteres. Su
comparación es exacta después de trim; no se eliminan acentos del código. El
orden es entero positivo y único dentro del código. Mesa ID también es texto
externo ≤ 50; `001` no se transforma en `1`.

La RPC inserta mesas e invitaciones sin IDs, captura los IDs generados mediante
`RETURNING` y crea invitados usando los mapas internos. Los códigos externos no
se persisten porque el esquema no posee columnas apropiadas. Por ello la primera
versión no puede reconciliar códigos de una importación anterior.

## 5. Validaciones del archivo

Configuración inicial propuesta: máximo 5 MiB, 5,000 filas de datos y una hoja
esperada llamada `Importación`. Los límites deben ser constantes configurables.

1. Nombre terminado exactamente en `.xlsx`; rechazar `.xls`, `.xlsm` y nombres
   con extensión doble engañosa.
2. Abrir como ZIP/XLSX válido, en modo lectura y `data_only=True`; cerrar siempre
   mediante context manager/finally.
3. Exigir hoja `Importación` y los nueve encabezados exactos en cualquier orden,
   sin vacíos, extras ni duplicados después de trim/BOM.
4. Rechazar archivo sin filas de datos; ignorar filas completamente vacías y
   advertir cuando una fila vacía sea intermedia.
5. Rechazar celdas de error y fórmulas cuyo valor calculado sea NULL/no
   disponible. Nunca ejecutar macros, enlaces ni fórmulas.
6. Tratar códigos, teléfono y Mesa ID como texto. Si Excel ya convirtió un valor
   numérico y perdió ceros, emitir error: el parser no puede reconstruirlos.
7. Rechazar fechas, objetos o booleanos de Excel en columnas incompatibles.

No se necesita pandas. `openpyxl` es la opción recomendada, pero no figura en
`requirements.txt` ni se instala en esta fase. Para implementar habrá que fijar
una versión compatible con Python 3.14.6, justificarla y obtener aprobación.

## 6. Validaciones por fila y grupo

### Fila

- Código requerido, texto normalizado con trim, ≤ 50.
- Destinatario requerido, trim, ≤ 100; idéntico en todas las filas del código.
- Orden requerido, entero positivo (no decimal, booleano ni notación ambigua),
  único dentro de la invitación.
- Nombre requerido, trim, ≤ 80 y único en todo el archivo según la misma
  normalización SQL: minúsculas, sin acentos, trim y espacios colapsados.
- Teléfono opcional, texto ≤ 20; conservar `+`, espacios y ceros. No convertir a
  número. Una celda numérica es error, no autocorrección.
- Email opcional, ≤ 254, sin espacios laterales y con validación básica de una
  sola `@`, partes no vacías y dominio con punto; no se pretende RFC completo.
- Principal acepta `Sí`, `Si` y `No`, ignorando espacios, caso y acentos; ningún
  otro valor ni celda vacía.
- Mesa ID y nombre se proporcionan ambos o ninguno. Nombre ≤ 30.

### Invitación

- Exactamente un principal. Esta es una regla de importación más estricta que el
  esquema, que solo impide dos.
- Destinatario único, órdenes únicos, y una o más filas.
- Puestos reservados igual al número de invitados válidos del grupo.
- Un código contradictorio invalida todo el archivo, no solo sus filas.

### Mesa

- Un código externo siempre tiene un único nombre después de trim.
- Un mismo nombre normalizado no puede pertenecer a dos códigos externos, aunque
  el esquema no tenga UNIQUE; evita crear duplicados visuales.
- Varios invitados pueden compartir mesa e invitados pueden quedar sin mesa.
- No se crean mesas vacías: la plantilla es por invitado y solo genera códigos
  referenciados por filas válidas.
- La FK y la RPC vuelven a garantizar cuenta/evento.
- Si `eve_cant_mesas` no es NULL y el archivo lo excede, bloquear. Si es NULL, no
  existe capacidad de mesas que validar. Decidir en implementación si una cifra
  superior ya configurada debe ser solo advertencia o coincidencia exacta.

### Evento y roles

- Exigir usuario EventPlus Activo, evento autorizado, cuenta/evento coincidentes,
  evento `Activo` y fase exactamente `Pre_evento`.
- `En_proceso`, `Post_evento`, `Cerrado`, evento suspendido o inactivo: bloqueo.
- Master puede importar dentro de su alcance vigente; Administrador únicamente
  en su cuenta autorizada. Operador y Consulta: opción oculta y rechazo en
  servicio/RPC. El módulo no existe en CHECKIN.

## 7. Duplicados y conflictos

Política v1: **solo evento vacío**. Antes de confirmar y de nuevo dentro de la
transacción, no debe existir ninguna fila de mesa, invitación o invitado para la
cuenta/evento, sin importar su estado. Incluir mesas existentes en el bloqueo es
la opción segura porque el código externo no se persiste y no hay forma inequívoca
de decidir si debe reutilizar una mesa por nombre.

- Archivo repetido: segundo intento bloqueado por evento no vacío.
- Invitado duplicado normalizado: error previo y defensa del índice SQL.
- Principal duplicado: error de grupo y defensa del índice parcial.
- Código externo repetido con datos coherentes: forma el mismo grupo; con datos
  contradictorios: error.
- Coincidencia potencial con registros existentes: bloqueo total, sin mezcla.
- No hay modo agregar, reemplazar, borrar ni “upsert” en v1.

Una versión posterior podrá guardar claves externas en una tabla de importación
o agregar modo de conciliación, pero requiere cambio explícito de esquema y regla
de negocio. Nunca se reemplazará automáticamente información existente.

## 8. Arquitectura transaccional y RPC futura

Flujo obligatorio:

1. Python valida íntegramente y crea un payload canónico.
2. Al confirmar, vuelve a validar contexto/rol/fase y llama una sola RPC.
3. La RPC deriva usuario con `auth.uid()` / `evp_usuario_id_actual()`.
4. Cuenta y evento pueden enviarse como selectores separados porque PostgreSQL
   no conoce el “evento activo” de la Page, pero se consideran datos no confiables
   y nunca autoridad. El payload JSON no contiene cuenta/evento.
5. La RPC verifica usuario, Master/Admin, tenant, evento Activo/Pre_evento y
   vacío bajo locks adecuados.
6. Crea mesas únicas, invitaciones y luego invitados, capturando IDs generados.
7. Comprueba conteos e invariantes y retorna resumen/mapas de referencia.
8. Cualquier excepción aborta la función y hace rollback total.

Firma conceptual, no SQL aplicado:

```text
public.evp_importar_evento_desde_json(
    p_cuenta_id integer,
    p_evento_id integer,
    p_payload jsonb,
    p_idempotency_key text
) -> jsonb
```

`p_idempotency_key` sería el SHA-256 del archivo más usuario/evento o un UUID de
operación y exige almacenamiento persistente para idempotencia real; como no hay
tabla de importaciones, queda como decisión de diseño SQL futura. Sin ella, el
bloqueo por evento vacío evita repeticiones después del primer éxito.

La RPC futura debe usar `SECURITY DEFINER`, `search_path` fijo, revocar EXECUTE a
`public`/`anon`, conceder solo a `authenticated`, validar tipos/longitudes además
de confiar en constraints, limitar tamaño JSON, no aceptar IDs internos del
cliente y no capturar excepciones que impidan rollback. Los triggers actuales se
mantienen como generadores. No se debe simular atomicidad con rollback manual en
Python ni con múltiples llamadas PostgREST.

Respuesta conceptual:

```json
{
  "ok": true,
  "mesas_creadas": 8,
  "invitaciones_creadas": 25,
  "invitados_creados": 120,
  "external_invitation_map": {},
  "external_table_map": {}
}
```

Los mapas pueden omitirse de la respuesta pública si no son necesarios y para
reducir exposición de IDs internos.

## 9. Flujo UI de tres pasos

Solo FULL y visible para Master/Admin:

1. **Seleccionar archivo:** nombre, tamaño, evento y cuenta actuales, botón
   Seleccionar Excel y descarga de plantilla. Cambiar evento invalida el archivo.
2. **Validar y previsualizar:** procesamiento local, tarjetas con filas,
   invitaciones, invitados, mesas, errores y advertencias; tabla paginada; filtros
   por severidad/fila; descarga de errores. Sin escrituras remotas.
3. **Confirmar:** resumen inmutable, evento/cuenta, advertencia “todo o nada”,
   checkbox de confirmación, botón Importar, progreso no cancelable una vez
   enviada la RPC y resultado final. Un nuevo check remoto puede bloquear aunque
   el preview fuera válido si el evento cambió concurrentemente.

Estados: sin evento, seleccionando, leyendo, inválido, listo, confirmando,
importando, éxito y error controlado. Nunca mostrar traceback ni habilitar
Importar con errores. Advertencias no bloqueantes deben requerir reconocimiento.

## 10. Archivo de errores

CSV UTF-8 con BOM es suficiente para v1 y evita otra escritura XLSX durante el
preview. Columnas: `fila`, `columna`, `valor`, `tipo_error`, `mensaje`,
`severidad`. Se neutralizan valores que comiencen con `=`, `+`, `-` o `@`
anteponiendo apóstrofo para evitar inyección de fórmulas al abrir en Excel. Los
valores sensibles se truncan razonablemente.

Severidades: `ERROR` bloquea; `ADVERTENCIA` requiere revisión. Ejemplos:

```text
7,Es invitado principal?,Tal vez,valor_no_permitido,Use Sí/Si/No,ERROR
12,Mesa ID,3,mesa_inconsistente,El código tiene dos nombres,ERROR
20,Nombre del invitado,Juan Pérez,nombre_duplicado,Duplicado normalizado,ERROR
```

## 11. Plantilla descargable

Se generará con `openpyxl` en memoria, sin ejemplos mezclados con datos reales:

- Hoja `Importación`: nueve encabezados exactos, fila congelada, autofiltro,
  anchos legibles, estilos sobrios y formato texto para códigos, teléfono y Mesa
  ID. Validación de lista `Sí,No` para principal (el lector también acepta `Si`).
- Hoja `Instrucciones`: descripción, obligatoriedad, máximo, ejemplo, valores
  permitidos, reglas de principal/mesa, límites y aviso para conservar códigos y
  teléfonos como texto.
- Los ejemplos, si se incluyen, estarán solo en Instrucciones; así no existe el
  riesgo de importarlos accidentalmente.

La descarga debe fijar Content-Type XLSX, nombre seguro y no incorporar cuenta,
evento, IDs internos ni datos reales.

## 12. Matriz de pruebas propuesta

| Área | Casos mínimos |
|---|---|
| Archivo | válido, vacío, hoja ausente, encabezados extra/faltantes/duplicados/desordenados, corrupto, `.xls`/`.xlsm`, límite de bytes/filas, fila vacía intermedia, fórmula no evaluada |
| Invitaciones | un/ningún/dos principales, destinatario contradictorio, orden repetido/no entero, código con cero inicial |
| Invitados | nombre vacío/largo/duplicado normalizado, acentos y espacios, teléfono `001...`, teléfono numérico rechazado, email inválido/largo, Sí/Si/No y valor inválido |
| Mesas | sin nombre, nombre sin ID, mismo ID con dos nombres, mismo nombre con dos IDs, sin mesa, capacidad del evento excedida |
| Conflictos | evento vacío, cada una de las tres tablas con datos activos o inactivos, archivo repetido, cambio concurrente tras preview |
| Roles | Master/Admin admitidos en alcance; Operador/Consulta rechazados en UI, servicio y RPC |
| Evento | Activo Pre_evento; En_proceso/Post_evento/Cerrado; suspendido/inactivo; cambio de evento durante preview |
| Transacción | fallo en mesa/invitación/invitado, constraint, timeout y concurrencia; siempre cero filas parciales; reintento seguro |
| Seguridad | payload con cuenta/evento/IDs internos, JSON sobredimensionado, llamada directa, EXECUTE anon, fórmula CSV, nombres maliciosos |
| UI | los tres pasos, preview paginada, descarga de errores/plantilla, doble clic, progreso, errores accesibles, FULL sí/CHECKIN no |

Las pruebas de RPC requerirán base de datos aislada o transacciones de prueba;
los fakes Python no demuestran atomicidad PostgreSQL.

## 13. Riesgos y decisiones pendientes

Riesgos principales:

- `MAX + 1` depende de triggers/advisory locks; solo es seguro si la RPC deja los
  IDs NULL y toda la carga permanece en una transacción.
- Los códigos externos no se persisten; no existe conciliación entre cargas.
- `openpyxl` aún no es dependencia y debe confirmarse compatible con Python
  3.14.6.
- `data_only=True` no calcula fórmulas; solo lee caché. Fórmulas sin caché deben
  bloquearse y puede requerirse una segunda apertura para detectarlas.
- La unicidad de nombres de invitados es por evento completo y normalización SQL;
  Python debe reproducirla o la RPC debe devolver el error exacto.
- No hay tabla de auditoría de importaciones ni clave idempotente persistente.
- RLS no aplicada: la RPC necesita un diseño y validación de seguridad propios
  antes de producción.

Decisiones pendientes antes de implementar:

1. Versión exacta aprobada de `openpyxl` y límites finales de bytes/filas.
2. Si `eve_cant_mesas` debe coincidir exactamente o solo ser un máximo.
3. Si se crea una tabla futura de lotes/claves externas para auditoría,
   idempotencia y futuras importaciones incrementales.
4. Nombre/firma definitiva de la RPC y detalle del resumen retornado.
5. Política final para caracteres permitidos en códigos externos.
6. Si el CSV de errores es suficiente o se exige XLSX.

## 14. Criterios de aceptación de la futura implementación

- Parser y plantilla con límites, cierre seguro y ninguna macro.
- Las nueve columnas permanecen como contrato y el contexto es la única fuente
  de tenant/evento.
- Preview completa sin escrituras y errores descargables.
- Exactamente un principal, nombres únicos normalizados y mapas externos seguros.
- Solo Master/Admin, FULL, evento Activo/Pre_evento y completamente vacío.
- Una sola RPC atómica, revalidación server-side, rollback demostrado y ninguna
  escritura directa desde Python.
- Operador/Consulta/CHECKIN sin opción y con rechazo de backend.
- Pruebas de archivo, reglas, seguridad, concurrencia y transacción aprobadas.
- Documentación/RLS actualizadas y SQL revisado antes de cualquier aplicación.

Hasta cumplir estos criterios, el módulo debe seguir figurando como **diseñado,
no implementado**.
