# Validación de metadatos previa a roles y RLS

Estado: pendiente de ejecución remota. Ningún SQL de este documento ni de las
migraciones propuestas fue aplicado.

## Lo confirmado localmente

El contrato `EVENTPLUS_SCHEMA_CONTEXT_v1_1.md` documenta
`evp_ucu_usuario_cuenta.ucu_rol` como `varchar(20) NOT NULL`; no documenta un
enum. Los valores funcionales vigentes son `Administrador`, `Operador` y
`Consulta`. El repositorio no contiene el DDL fuente que permita confirmar el
nombre o la definición real de un `CHECK`.

## Metadatos que deben capturarse antes de aplicar

```sql
select column_name, data_type, udt_schema, udt_name, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name = 'evp_ucu_usuario_cuenta'
  and column_name = 'ucu_rol';

select con.conname, pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'evp_ucu_usuario_cuenta'
  and con.contype = 'c';
```

Si el tipo remoto resulta enum o el `CHECK` contiene reglas adicionales, se
debe detener la migración y redactar una variante basada en esa evidencia. La
migración propuesta valida el tipo y aborta ante una definición inesperada.

## Matriz RLS de Consulta

- SELECT de cuenta: relación activa en `evp_ucu_usuario_cuenta`.
- SELECT de evento: relación de cuenta activa y asignación activa en
  `evp_uev_usuario_evento`, igual que Operador.
- SELECT de invitaciones, mesas e invitados: únicamente dentro de esos eventos.
- INSERT, UPDATE y DELETE: siempre denegados.
- RPC de escritura: sin `EXECUTE` efectivo y con comprobación interna que
  excluya `Consulta`.
- Asignaciones y roles: no puede crearlos, cambiarlos, borrarlos ni
  autoasignarse.

Casos mínimos de staging: Consulta A1 lee A1, no A2 ni cuenta B; alterar IDs no
amplía acceso; no confirma ni revierte llegadas; no crea, edita o desactiva
invitados; Operador, Administrador y Master conservan su matriz.
