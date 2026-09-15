-- EVKOR QR-1B0: auditoria de catalogos y datos no sensibles.
-- Ejecutar manualmente, como una sola consulta, en Supabase SQL Editor.
-- Cada bloque devuelve un conjunto de resultados independiente.

-- 1. Estado de RLS, FORCE RLS y propietario de las tablas principales.
select
    n.nspname as esquema,
    c.relname as tabla,
    c.relrowsecurity as rls_habilitado,
    c.relforcerowsecurity as force_rls,
    owner_role.rolname as propietario
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid = c.relnamespace
join pg_catalog.pg_roles owner_role on owner_role.oid = c.relowner
where n.nspname = 'public'
  and c.relname in (
      'evp_cta_cuenta',
      'evp_eve_evento',
      'evp_inv_invitacion',
      'evp_ivt_invitado',
      'evp_mes_mesa'
  )
order by c.relname;

-- 2. Privilegios efectivos de los roles de API sobre las tablas principales.
with roles_objetivo(rol) as (
    values ('anon'), ('authenticated')
), privilegios(privilegio) as (
    values
        ('S' || 'ELECT'),
        ('IN' || 'SERT'),
        ('UP' || 'DATE'),
        ('DE' || 'LETE'),
        ('TRUN' || 'CATE'),
        ('REF' || 'ERENCES'),
        ('TRIG' || 'GER')
), tablas(tabla) as (
    values
        ('public.evp_cta_cuenta'),
        ('public.evp_eve_evento'),
        ('public.evp_inv_invitacion'),
        ('public.evp_ivt_invitado'),
        ('public.evp_mes_mesa')
)
select
    r.rol,
    t.tabla,
    p.privilegio,
    pg_catalog.has_table_privilege(r.rol, t.tabla, p.privilegio) as efectivo
from roles_objetivo r
cross join tablas t
cross join privilegios p
order by t.tabla, r.rol, p.privilegio;

-- 3. Concesiones visibles para los roles habilitados.
select
    grantor,
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name in (
      'evp_cta_cuenta',
      'evp_eve_evento',
      'evp_inv_invitacion',
      'evp_ivt_invitado',
      'evp_mes_mesa'
  )
  and grantee in ('anon', 'authenticated')
order by table_name, grantee, privilege_type;

-- 4. Politicas RLS reales, incluidas expresiones de acceso.
select
    schemaname as esquema,
    tablename as tabla,
    policyname as politica,
    permissive as modo,
    roles,
    cmd as operacion,
    qual as condicion_filas,
    with_check as condicion_nuevas_filas
from pg_catalog.pg_policies
where schemaname = 'public'
  and tablename in (
      'evp_cta_cuenta',
      'evp_eve_evento',
      'evp_inv_invitacion',
      'evp_ivt_invitado',
      'evp_mes_mesa'
  )
order by tablename, policyname;

-- 5. Definicion real de inv_token_qr_invitacion.
select
    c.table_schema as esquema,
    c.table_name as tabla,
    c.column_name as columna,
    c.data_type as tipo,
    c.udt_name as tipo_interno,
    c.character_maximum_length as longitud_declarada,
    c.is_nullable as nullable,
    c.column_default as valor_predeterminado
from information_schema.columns c
where c.table_schema = 'public'
  and c.table_name = 'evp_inv_invitacion'
  and c.column_name = 'inv_token_qr_invitacion';

-- 6. Restricciones unicas reales que incluyen exactamente el campo auditado.
select
    con.conname as restriccion,
    pg_catalog.pg_get_constraintdef(con.oid, true) as definicion,
    con.convalidated as validada
from pg_catalog.pg_constraint con
join pg_catalog.pg_class rel on rel.oid = con.conrelid
join pg_catalog.pg_namespace n on n.oid = rel.relnamespace
where n.nspname = 'public'
  and rel.relname = 'evp_inv_invitacion'
  and con.contype = 'u'
  and con.conkey = array[
      (
          select a.attnum
          from pg_catalog.pg_attribute a
          where a.attrelid = rel.oid
            and a.attname = 'inv_token_qr_invitacion'
            and not a.attisdropped
      )::smallint
  ];

-- 7. Resumen de poblacion del campo. No devuelve valores del token.
select
    count(*) as invitaciones_total,
    count(inv_token_qr_invitacion) as tokens_no_nulos,
    count(*) filter (where inv_token_qr_invitacion is null) as tokens_nulos,
    min(length(inv_token_qr_invitacion)) as longitud_minima,
    max(length(inv_token_qr_invitacion)) as longitud_maxima,
    count(distinct inv_token_qr_invitacion) as tokens_distintos
from public.evp_inv_invitacion;

-- 8. Duplicados identificados solo con un numero secuencial y longitud.
with grupos_duplicados as (
    select
        inv_token_qr_invitacion,
        length(inv_token_qr_invitacion) as longitud,
        count(*) as repeticiones
    from public.evp_inv_invitacion
    where inv_token_qr_invitacion is not null
    group by inv_token_qr_invitacion
    having count(*) > 1
)
select
    row_number() over (order by repeticiones desc, longitud) as grupo_duplicado,
    longitud,
    repeticiones
from grupos_duplicados
order by grupo_duplicado;

-- 9. Muestra segura de formatos; nunca devuelve un token completo.
select
    case
        when inv_token_qr_invitacion ~ '^[0-9]+$' then 'numerico'
        when inv_token_qr_invitacion ~ '^[A-Z0-9]+$' then 'alfanumerico_mayusculas'
        when inv_token_qr_invitacion ~ '^[a-z0-9]+$' then 'alfanumerico_minusculas'
        when inv_token_qr_invitacion ~ '^[[:alnum:]]+$' then 'alfanumerico_mixto'
        else 'otros_caracteres'
    end as patron,
    left(inv_token_qr_invitacion, 1) || repeat('*', least(3, greatest(length(inv_token_qr_invitacion) - 1, 0))) as muestra_enmascarada,
    length(inv_token_qr_invitacion) as longitud,
    count(*) as cantidad
from public.evp_inv_invitacion
where inv_token_qr_invitacion is not null
group by patron, muestra_enmascarada, longitud
order by cantidad desc, patron, longitud
limit 25;

-- 10. Funciones publicas relacionadas por nombre, sin mostrar su cuerpo.
select
    n.nspname as esquema,
    p.proname as funcion,
    pg_catalog.pg_get_function_identity_arguments(p.oid) as argumentos,
    pg_catalog.pg_get_function_result(p.oid) as retorno,
    case when p.prosecdef then 'definer' else 'invoker' end as contexto_seguridad,
    owner_role.rolname as propietario,
    l.lanname as lenguaje
from pg_catalog.pg_proc p
join pg_catalog.pg_namespace n on n.oid = p.pronamespace
join pg_catalog.pg_roles owner_role on owner_role.oid = p.proowner
join pg_catalog.pg_language l on l.oid = p.prolang
where n.nspname = 'public'
  and p.proname ~* '(invitacion|invitado|llegada|usuario_evento|usuario_cuenta|qr)'
order by p.proname, argumentos;

-- 11. Privilegio efectivo de ejecucion para funciones relacionadas.
with roles_objetivo(rol) as (
    values ('anon'), ('authenticated')
), funciones as (
    select
        p.oid,
        n.nspname,
        p.proname,
        pg_catalog.pg_get_function_identity_arguments(p.oid) as argumentos
    from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname ~* '(invitacion|invitado|llegada|usuario_evento|usuario_cuenta|qr)'
)
select
    f.nspname as esquema,
    f.proname as funcion,
    f.argumentos,
    r.rol,
    pg_catalog.has_function_privilege(r.rol, f.oid, 'EXE' || 'CUTE') as ejecucion_efectiva
from funciones f
cross join roles_objetivo r
order by f.proname, f.argumentos, r.rol;

-- 12. Presencia y seguridad de helpers de autorizacion conocidos.
with helpers(nombre) as (
    values
        ('evp_usuario_id_actual'),
        ('evp_es_usuario_master'),
        ('evp_tiene_acceso_cuenta'),
        ('evp_puede_ver_evento'),
        ('evp_rls_usuario_id'),
        ('evp_rls_es_master'),
        ('evp_rls_rol_cuenta'),
        ('evp_rls_tiene_cuenta'),
        ('evp_rls_tiene_evento'),
        ('evp_rls_puede_administrar_evento'),
        ('evp_rls_puede_operar_evento')
)
select
    h.nombre,
    p.oid is not null as existe,
    pg_catalog.pg_get_function_identity_arguments(p.oid) as argumentos,
    case
        when p.oid is null then null
        when p.prosecdef then 'definer'
        else 'invoker'
    end as contexto_seguridad,
    owner_role.rolname as propietario
from helpers h
left join pg_catalog.pg_proc p on p.proname = h.nombre
left join pg_catalog.pg_namespace n on n.oid = p.pronamespace and n.nspname = 'public'
left join pg_catalog.pg_roles owner_role on owner_role.oid = p.proowner
where p.oid is null or n.nspname = 'public'
order by h.nombre, argumentos;

-- 13. Comparacion con las politicas esperadas por la propuesta RLS fase 1.
with tablas(tabla) as (
    values
        ('evp_cta_cuenta'),
        ('evp_eve_evento'),
        ('evp_inv_invitacion'),
        ('evp_ivt_invitado'),
        ('evp_mes_mesa')
), politicas_esperadas(tabla, politica) as (
    values
        ('evp_cta_cuenta', 'evp_rls_cta_select'),
        ('evp_cta_cuenta', 'evp_rls_cta_update'),
        ('evp_eve_evento', 'evp_rls_eve_select'),
        ('evp_eve_evento', 'evp_rls_eve_insert'),
        ('evp_eve_evento', 'evp_rls_eve_update'),
        ('evp_eve_evento', 'evp_rls_eve_delete'),
        ('evp_inv_invitacion', 'evp_rls_inv_select'),
        ('evp_inv_invitacion', 'evp_rls_inv_mutate'),
        ('evp_ivt_invitado', 'evp_rls_ivt_select'),
        ('evp_ivt_invitado', 'evp_rls_ivt_insert_admin'),
        ('evp_ivt_invitado', 'evp_rls_ivt_update_admin'),
        ('evp_ivt_invitado', 'evp_rls_ivt_delete'),
        ('evp_mes_mesa', 'evp_rls_mes_all')
), estado_tabla as (
    select
        t.tabla,
        c.oid is not null as tabla_existe,
        coalesce(c.relrowsecurity, false) as rls_habilitado
    from tablas t
    left join pg_catalog.pg_namespace n on n.nspname = 'public'
    left join pg_catalog.pg_class c on c.relnamespace = n.oid and c.relname = t.tabla
), conteo_esperado as (
    select tabla, count(*) as cantidad
    from politicas_esperadas
    group by tabla
), conteo_real as (
    select
        p.tablename as tabla,
        count(*) filter (where pe.politica is not null) as coincidentes,
        count(*) filter (where pe.politica is null) as adicionales
    from pg_catalog.pg_policies p
    left join politicas_esperadas pe
      on pe.tabla = p.tablename
     and pe.politica = p.policyname
    where p.schemaname = 'public'
      and p.tablename in (select tabla from tablas)
    group by p.tablename
), resumen as (
    select
        e.tabla,
        e.tabla_existe,
        e.rls_habilitado,
        coalesce(ce.cantidad, 0) as politicas_esperadas,
        coalesce(cr.coincidentes, 0) as politicas_coincidentes,
        coalesce(cr.adicionales, 0) as politicas_adicionales
    from estado_tabla e
    left join conteo_esperado ce on ce.tabla = e.tabla
    left join conteo_real cr on cr.tabla = e.tabla
)
select
    tabla,
    tabla_existe,
    rls_habilitado,
    politicas_esperadas,
    politicas_coincidentes,
    politicas_adicionales,
    case
        when not tabla_existe then 'requiere investigacion'
        when not rls_habilitado and politicas_coincidentes = 0 then 'migracion no aplicada'
        when rls_habilitado
         and politicas_coincidentes = politicas_esperadas
         and politicas_adicionales = 0 then 'coincide'
        when rls_habilitado
         and politicas_coincidentes = politicas_esperadas
         and politicas_adicionales > 0 then 'base mas avanzada que repositorio'
        else 'requiere investigacion'
    end as clasificacion_preliminar
from resumen
order by tabla;

-- 14. Existencia previa de la tabla QR futura.
select
    pg_catalog.to_regclass('public.evp_iqr_invitacion_qr') is not null as tabla_qr_ya_existe;
