# RPC transaccional de importación Excel (7C)

Estado: migración e integración Python preparadas; RPC no aplicada.

## Firma y seguridad

```sql
public.evp_importar_evento_desde_json(
  p_cuenta_id integer,
  p_evento_id integer,
  p_payload jsonb,
  p_payload_hash text
) returns jsonb
```

La función es `SECURITY DEFINER`, con el `search_path` mínimo fijado a
`pg_catalog`. Todos los objetos de aplicación están calificados con `public.` y
la identidad se deriva exclusivamente de `auth.uid()`. Exige usuario/cuenta
activos y Master o una relación de cuenta activa con rol Administrador. Igual
que el contexto actual de EventPlus, un Administrador accede a todos los
eventos de su cuenta y no necesita una relación en `evp_uev_usuario_evento`.
`PUBLIC` y `anon` no tienen EXECUTE; solo `authenticated`.
No se conceden INSERT directos adicionales y RLS no se activa en esta tarea.

## Correspondencia con `esquema.sql`

La RPC escribe únicamente columnas existentes y respeta sus tipos y límites:
mesa `varchar(30)`; destinatario `varchar(100)`; puestos `integer`; nombre de
invitado `varchar(80)`; email `varchar(254)`; teléfono `varchar(20)`; claves e
IDs `integer`; auditoría `uuid`; flags `boolean`; estado `varchar(15)` con valor
`Activo`. Omite los IDs secuenciales para activar `trg_evp_mes_set_id`,
`trg_evp_inv_set_id` y `trg_evp_ivt_set_id`; también omite el UUID y timestamps
que tienen defaults. Las FK compuestas conservan cuenta/evento/invitación/mesa.

Se respetan los checks de puestos no negativos, estado y puesto positivo, y los
índices únicos de nombre normalizado y principal por invitación. La validación
preventiva reproduce `public.evp_normalizar_texto(text)` y rechaza además un
resultado NULL o vacío. No se hallaron nombres de columna, tipos, longitudes,
constraints, triggers ni valores insertados incompatibles con `esquema.sql`.
Las reglas de contrato adicionales (límites de payload, códigos externos,
órdenes, un principal y evento inicialmente vacío) pertenecen a la importación;
no son constraints nuevos del esquema.

## Atomicidad y concurrencia

La llamada toma `pg_try_advisory_xact_lock(cuenta, evento)` y bloquea el evento
con `SELECT ... FOR UPDATE`. Verifica que no exista ninguna mesa, invitación ni
invitado, incluido estado Inactivo. Una segunda llamada concurrente recibe
`CONCURRENT_IMPORT`. Toda excepción sale de la función y PostgreSQL revierte la
sentencia completa.

Orden: mesas y mapa de código externo a `mes_mesa_id`; invitaciones y captura de
`inv_invitacion_id`; invitados relacionados con ambos mapas. Los IDs se omiten
para que actúen los triggers existentes. Códigos externos y orden no se
persisten.

## Contrato JSON v1

El objeto contiene `version: 1`, `mesas[]` (`codigo_externo`, `nombre`) e
`invitaciones[]` (`codigo_externo`, `destinatario`, `puestos_reservados`,
`invitados[]`). Cada invitado contiene `orden`, `nombre`, `telefono`, `email`,
`es_principal` y `mesa_codigo`. No contiene rol, usuario, estados, cuenta/evento
ni IDs internos. Python serializa canónicamente y calcula SHA-256. SQL solo
valida que `p_payload_hash` tenga 64 caracteres hexadecimales: **no recalcula el
hash ni verifica que corresponda a `p_payload`**. Este parámetro liga la
previsualización en el cliente, pero no es una medida de autorización ni de
integridad del lado servidor.

SQL revalida estructura, 10 MiB, 5.000 invitados, longitudes, códigos, nombres
normalizados, órdenes, exactamente un principal, puestos, mesas referenciadas,
evento Activo/Pre_evento y capacidad opcional `eve_cant_mesas`.

Errores: `IMPORT_FORBIDDEN`, `EVENT_NOT_FOUND`, `EVENT_NOT_ACTIVE`,
`EVENT_NOT_PRE_EVENT`, `EVENT_NOT_EMPTY`, `INVALID_PAYLOAD`, `DUPLICATE_GUEST`,
`INVALID_TABLE_REFERENCE`, `CONCURRENT_IMPORT` e `IMPORT_INTERNAL_ERROR`. Este
último identifica fallos inesperados que no deben presentarse como errores del
payload.

## Aplicación manual

1. Abra Supabase SQL Editor en el proyecto correcto y confirme que es un entorno
   controlado.
2. Ejecute completo `supabase/migrations/202608040001_excel_import_rpc.sql`.
3. No ejecute `scripts/test_excel_import_rpc.sql` en producción; sustituya sus
   placeholders en un evento exclusivo de prueba.
4. Verifique firma y privilegios:

```sql
select p.oid::regprocedure as firma,
       pg_get_userbyid(p.proowner) as propietario,
       p.prosecdef as security_definer,
       p.proconfig as configuracion,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') as execute_authenticated,
       has_function_privilege('anon', p.oid, 'EXECUTE') as execute_anon,
       coalesce((select bool_or(a.privilege_type = 'EXECUTE')
                 from pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) a
                 where a.grantee = 0), false) as execute_public
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and p.proname='evp_importar_evento_desde_json';
```

Debe mostrar `security_definer=true`, `search_path=pg_catalog`, EXECUTE para
authenticated y false para anon y PUBLIC.
Compruebe 2/2/4, principales, puestos y flags con el guion SQL. Para rollback,
ejecute `202608040001_excel_import_rpc_rollback.sql` y repita la consulta: no
debe retornar función.

La prueba de integración requiere además provocar un error en el último
invitado y confirmar conteos 0/0/0, y dos sesiones simultáneas donde solo una
importe.
