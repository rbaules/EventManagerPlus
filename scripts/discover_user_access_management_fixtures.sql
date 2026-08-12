-- Descubrimiento READ-ONLY de fixtures para test_user_access_management_rpc.sql.
-- Ejecutar manualmente en Supabase SQL Editor. No prepara ni modifica datos.

-- A. MASTER CANDIDATES
select
  u.usr_usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_usuario_auth_uuid,
  u.usr_estado as estado
from public.evp_usr_usuario u
where u.usr_es_usuario_master = true
  and u.usr_estado = 'Activo'
  and u.usr_usuario_auth_uuid is not null
order by u.usr_nombre_usuario, u.usr_email;

-- B. ADMIN CANDIDATES
-- Una fila identifica conjuntamente ADMIN_A y su CUENTA_A.
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_usuario_auth_uuid as auth_uuid,
  uc.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as nombre_cuenta,
  uc.ucu_rol as rol,
  uc.ucu_estado as estado_relacion
from public.evp_usr_usuario u
join public.evp_ucu_usuario_cuenta uc
  on uc.ucu_usuario_id = u.usr_usuario_id
join public.evp_cta_cuenta c
  on c.cta_cuenta_id = uc.ucu_cuenta_id
where u.usr_estado = 'Activo'
  and u.usr_es_usuario_master = false
  and u.usr_usuario_auth_uuid is not null
  and uc.ucu_rol = 'Administrador'
  and uc.ucu_estado = 'Activo'
  and c.cta_estado = 'Activo'
order by c.cta_nombre_cuenta, u.usr_nombre_usuario, u.usr_email;

-- C. ACTIVE ACCOUNTS
-- El esquema no contiene una clasificación confiable de cuenta crítica/de prueba.
select
  c.cta_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as nombre
from public.evp_cta_cuenta c
where c.cta_estado = 'Activo'
order by c.cta_nombre_cuenta, c.cta_cuenta_id;

-- D. ACTIVE EVENTS
-- Elegir EVENTO_A1 y EVENTO_A2 con el mismo cuenta_id de CUENTA_A.
select
  e.eve_evento_id as evento_id,
  e.eve_nombre_evento as nombre,
  e.eve_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as nombre_cuenta
from public.evp_eve_evento e
join public.evp_cta_cuenta c
  on c.cta_cuenta_id = e.eve_cuenta_id
where e.eve_estado = 'Activo'
  and c.cta_estado = 'Activo'
order by c.cta_nombre_cuenta, e.eve_nombre_evento, e.eve_evento_id;

-- E. MULTI-ACCOUNT CANDIDATES
-- Cada fila es una combinación lista para elegir:
-- ADMIN_A administra CUENTA_A; USUARIO_MULTI es Administrador en CUENTA_B y
-- no tiene ninguna UCU en CUENTA_A. No se prepara ningún estado aquí.
with admin_a as (
  select
    actor.usr_usuario_id as admin_a_id,
    actor.usr_nombre_usuario as admin_a_nombre,
    actor.usr_email as admin_a_email,
    actor.usr_usuario_auth_uuid as admin_a_auth_uuid,
    auc.ucu_cuenta_id as cuenta_a_id,
    ca.cta_nombre_cuenta as cuenta_a_nombre
  from public.evp_usr_usuario actor
  join public.evp_ucu_usuario_cuenta auc
    on auc.ucu_usuario_id = actor.usr_usuario_id
   and auc.ucu_rol = 'Administrador'
   and auc.ucu_estado = 'Activo'
  join public.evp_cta_cuenta ca
    on ca.cta_cuenta_id = auc.ucu_cuenta_id
   and ca.cta_estado = 'Activo'
  where actor.usr_estado = 'Activo'
    and actor.usr_es_usuario_master = false
    and actor.usr_usuario_auth_uuid is not null
)
select
  a.admin_a_id,
  a.admin_a_nombre,
  a.admin_a_email,
  a.admin_a_auth_uuid,
  a.cuenta_a_id,
  a.cuenta_a_nombre,
  target.usr_usuario_id as usuario_multi_id,
  target.usr_nombre_usuario as usuario_multi_nombre,
  target.usr_email as usuario_multi_email,
  target.usr_estado as usuario_multi_estado,
  target.usr_usuario_auth_uuid as usuario_multi_auth_uuid,
  ub.ucu_cuenta_id as cuenta_b_id,
  cb.cta_nombre_cuenta as cuenta_b_nombre,
  ub.ucu_rol as rol_en_cuenta_b,
  ub.ucu_estado as estado_en_cuenta_b,
  'Sin UCU en Cuenta A'::text as precondicion_cuenta_a
from admin_a a
join public.evp_ucu_usuario_cuenta ub
  on ub.ucu_cuenta_id <> a.cuenta_a_id
 and ub.ucu_rol = 'Administrador'
 and ub.ucu_estado = 'Activo'
join public.evp_usr_usuario target
  on target.usr_usuario_id = ub.ucu_usuario_id
join public.evp_cta_cuenta cb
  on cb.cta_cuenta_id = ub.ucu_cuenta_id
 and cb.cta_estado = 'Activo'
where target.usr_es_usuario_master = false
  and target.usr_estado in ('Activo', 'Preregistrado')
  and target.usr_usuario_id <> a.admin_a_id
  and not exists (
    select 1
    from public.evp_ucu_usuario_cuenta ua
    where ua.ucu_usuario_id = target.usr_usuario_id
      and ua.ucu_cuenta_id = a.cuenta_a_id
  )
order by a.cuenta_a_nombre, cb.cta_nombre_cuenta, target.usr_nombre_usuario;

-- F. SAME-ACCOUNT ADMIN CANDIDATES
-- Cada fila ofrece ADMIN_A y un USUARIO_ADMIN_A distinto en la misma cuenta.
-- Resultado vacío = no existe un segundo Administrador/Activo en esa cuenta.
select
  actor.usr_usuario_id as admin_a_id,
  actor.usr_nombre_usuario as admin_a_nombre,
  actor.usr_email as admin_a_email,
  actor.usr_usuario_auth_uuid as admin_a_auth_uuid,
  actor_uc.ucu_cuenta_id as cuenta_a_id,
  c.cta_nombre_cuenta as cuenta_a_nombre,
  target.usr_usuario_id as usuario_admin_a_id,
  target.usr_nombre_usuario as usuario_admin_a_nombre,
  target.usr_email as usuario_admin_a_email,
  target.usr_usuario_auth_uuid as usuario_admin_a_auth_uuid,
  target_uc.ucu_rol as rol_en_cuenta_a,
  target_uc.ucu_estado as estado_relacion
from public.evp_usr_usuario actor
join public.evp_ucu_usuario_cuenta actor_uc
  on actor_uc.ucu_usuario_id = actor.usr_usuario_id
 and actor_uc.ucu_rol = 'Administrador'
 and actor_uc.ucu_estado = 'Activo'
join public.evp_cta_cuenta c
  on c.cta_cuenta_id = actor_uc.ucu_cuenta_id
 and c.cta_estado = 'Activo'
join public.evp_ucu_usuario_cuenta target_uc
  on target_uc.ucu_cuenta_id = actor_uc.ucu_cuenta_id
 and target_uc.ucu_rol = 'Administrador'
 and target_uc.ucu_estado = 'Activo'
 and target_uc.ucu_usuario_id <> actor.usr_usuario_id
join public.evp_usr_usuario target
  on target.usr_usuario_id = target_uc.ucu_usuario_id
where actor.usr_estado = 'Activo'
  and actor.usr_es_usuario_master = false
  and actor.usr_usuario_auth_uuid is not null
  and target.usr_estado in ('Activo', 'Preregistrado')
  and target.usr_es_usuario_master = false
order by c.cta_nombre_cuenta, actor.usr_nombre_usuario, target.usr_nombre_usuario;

-- G. TRANSITION USER CANDIDATES
-- Elegir seis usuario_id distintos. resumen_ucu y resumen_uev muestran qué existe;
-- el test funcional preparará dentro de BEGIN/ROLLBACK el rol/estado exacto.
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_estado as estado,
  u.usr_usuario_auth_uuid as auth_uuid,
  coalesce(rel.resumen_ucu, '[]'::jsonb) as resumen_ucu,
  coalesce(evt.resumen_uev, '[]'::jsonb) as resumen_uev,
  case
    when rel.cantidad_ucu = 0 then 'Sin UCU; el test debe preparar la relación histórica'
    else 'Tiene UCU; el test sobrescribe rol/estado dentro de BEGIN/ROLLBACK'
  end as preparacion_requerida
from public.evp_usr_usuario u
left join lateral (
  select
    count(*) as cantidad_ucu,
    jsonb_agg(jsonb_build_object(
      'cuenta_id', uc.ucu_cuenta_id,
      'cuenta', c.cta_nombre_cuenta,
      'rol', uc.ucu_rol,
      'estado_relacion', uc.ucu_estado,
      'estado_cuenta', c.cta_estado
    ) order by c.cta_nombre_cuenta, uc.ucu_cuenta_id) as resumen_ucu
  from public.evp_ucu_usuario_cuenta uc
  join public.evp_cta_cuenta c
    on c.cta_cuenta_id = uc.ucu_cuenta_id
  where uc.ucu_usuario_id = u.usr_usuario_id
) rel on true
left join lateral (
  select jsonb_agg(jsonb_build_object(
    'cuenta_id', ue.uev_cuenta_id,
    'evento_id', ue.uev_evento_id,
    'evento', e.eve_nombre_evento,
    'estado_asignacion', ue.uev_estado,
    'estado_evento', e.eve_estado
  ) order by ue.uev_cuenta_id, ue.uev_evento_id) as resumen_uev
  from public.evp_uev_usuario_evento ue
  join public.evp_eve_evento e
    on e.eve_cuenta_id = ue.uev_cuenta_id
   and e.eve_evento_id = ue.uev_evento_id
  where ue.uev_usuario_id = u.usr_usuario_id
) evt on true
where u.usr_es_usuario_master = false
  and u.usr_estado in ('Activo', 'Preregistrado')
order by
  case when u.usr_usuario_auth_uuid is not null then 0 else 1 end,
  u.usr_nombre_usuario,
  u.usr_email;

-- H. DEFAULT CANDIDATES
-- Ayuda a elegir usuarios cuyo default se preservará o quedará NULL.
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_estado as estado,
  u.usr_usuario_auth_uuid as auth_uuid,
  u.usr_cuenta_id_default,
  cd.cta_nombre_cuenta as nombre_cuenta_default,
  u.usr_evento_id_default,
  ed.eve_nombre_evento as nombre_evento_default,
  ed.eve_estado as estado_evento_default
from public.evp_usr_usuario u
left join public.evp_cta_cuenta cd
  on cd.cta_cuenta_id = u.usr_cuenta_id_default
left join public.evp_eve_evento ed
  on ed.eve_cuenta_id = u.usr_cuenta_id_default
 and ed.eve_evento_id = u.usr_evento_id_default
where u.usr_es_usuario_master = false
  and u.usr_estado in ('Activo', 'Preregistrado')
order by
  case when u.usr_evento_id_default is not null then 0 else 1 end,
  u.usr_nombre_usuario,
  u.usr_email;
