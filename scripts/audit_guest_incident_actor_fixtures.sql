-- Auditoría READ-ONLY de actores para Novedades de invitados.
-- Solo SELECT/CTE/subconsultas. No prepara ni modifica datos.

-- A. PERFIL BASE DE LOS DOS ACTORES EN REVISIÓN
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_estado,
  u.usr_es_usuario_master,
  u.usr_usuario_auth_uuid as auth_uuid
from public.evp_usr_usuario u
where u.usr_usuario_id in (
  'a73f0cf1-e655-4126-bd4e-1020278af9c9'::uuid,
  '2ff1d503-9a55-4e3c-848b-573ee138c378'::uuid
)
order by u.usr_usuario_id;

-- B. TODAS LAS UCU DE LOS DOS ACTORES, SIN FILTRAR ESTADO NI ROL
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as usuario,
  u.usr_estado,
  u.usr_es_usuario_master,
  u.usr_usuario_auth_uuid as auth_uuid,
  r.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  c.cta_estado as estado_cuenta,
  r.ucu_rol,
  r.ucu_estado
from public.evp_usr_usuario u
left join public.evp_ucu_usuario_cuenta r
  on r.ucu_usuario_id=u.usr_usuario_id
left join public.evp_cta_cuenta c
  on c.cta_cuenta_id=r.ucu_cuenta_id
where u.usr_usuario_id in (
  'a73f0cf1-e655-4126-bd4e-1020278af9c9'::uuid,
  '2ff1d503-9a55-4e3c-848b-573ee138c378'::uuid
)
order by u.usr_usuario_id,r.ucu_cuenta_id;

-- C. TODAS LAS UEV DE LOS DOS ACTORES, INCLUIDAS HISTÓRICAS/INACTIVAS
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as usuario,
  u.usr_estado,
  u.usr_es_usuario_master,
  u.usr_usuario_auth_uuid as auth_uuid,
  a.uev_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  c.cta_estado as estado_cuenta,
  a.uev_evento_id as evento_id,
  e.eve_nombre_evento as evento,
  e.eve_fase_evento as fase_evento,
  e.eve_estado as estado_evento,
  a.uev_estado
from public.evp_usr_usuario u
left join public.evp_uev_usuario_evento a
  on a.uev_usuario_id=u.usr_usuario_id
left join public.evp_cta_cuenta c
  on c.cta_cuenta_id=a.uev_cuenta_id
left join public.evp_eve_evento e
  on e.eve_cuenta_id=a.uev_cuenta_id
 and e.eve_evento_id=a.uev_evento_id
where u.usr_usuario_id in (
  'a73f0cf1-e655-4126-bd4e-1020278af9c9'::uuid,
  '2ff1d503-9a55-4e3c-848b-573ee138c378'::uuid
)
order by u.usr_usuario_id,a.uev_cuenta_id,a.uev_evento_id;

-- D. TODAS LAS UCU ADMINISTRADOR, SIN FILTRAR INICIALMENTE POR ESTADO
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as usuario,
  u.usr_email as email,
  u.usr_estado,
  u.usr_es_usuario_master,
  u.usr_usuario_auth_uuid as auth_uuid,
  r.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  c.cta_estado as estado_cuenta,
  r.ucu_rol,
  r.ucu_estado
from public.evp_ucu_usuario_cuenta r
join public.evp_usr_usuario u
  on u.usr_usuario_id=r.ucu_usuario_id
join public.evp_cta_cuenta c
  on c.cta_cuenta_id=r.ucu_cuenta_id
where r.ucu_rol='Administrador'
order by r.ucu_estado,u.usr_estado,c.cta_estado,c.cta_nombre_cuenta,u.usr_nombre_usuario;

-- E. DESCOMPOSICIÓN DE POR QUÉ CADA UCU ADMINISTRADOR ENTRA O NO AL DISCOVERY B
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as usuario,
  u.usr_estado,
  u.usr_es_usuario_master,
  u.usr_usuario_auth_uuid as auth_uuid,
  r.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  c.cta_estado as estado_cuenta,
  r.ucu_estado,
  (u.usr_estado='Activo') as cumple_usuario_activo,
  (not u.usr_es_usuario_master) as cumple_no_master,
  (u.usr_usuario_auth_uuid is not null) as cumple_auth,
  (r.ucu_estado='Activo') as cumple_ucu_activa,
  (c.cta_estado='Activo') as cumple_cuenta_activa,
  (u.usr_estado='Activo' and not u.usr_es_usuario_master
    and u.usr_usuario_auth_uuid is not null
    and r.ucu_estado='Activo' and c.cta_estado='Activo') as aparece_en_discovery_b
from public.evp_ucu_usuario_cuenta r
join public.evp_usr_usuario u on u.usr_usuario_id=r.ucu_usuario_id
join public.evp_cta_cuenta c on c.cta_cuenta_id=r.ucu_cuenta_id
where r.ucu_rol='Administrador'
order by aparece_en_discovery_b desc,c.cta_nombre_cuenta,u.usr_nombre_usuario;

-- F. OPERADORES ACTUALES CON AUTH Y SUS UEV ACTIVAS REALES
-- La UCU Operador/Activa se exige antes de considerar cualquier UEV.
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as usuario,
  u.usr_email as email,
  u.usr_usuario_auth_uuid as auth_uuid,
  r.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  c.cta_estado as estado_cuenta,
  r.ucu_rol,
  r.ucu_estado,
  a.uev_evento_id as evento_id,
  e.eve_nombre_evento as evento,
  e.eve_fase_evento as fase_evento,
  e.eve_estado as estado_evento,
  a.uev_estado
from public.evp_usr_usuario u
join public.evp_ucu_usuario_cuenta r
  on r.ucu_usuario_id=u.usr_usuario_id
 and r.ucu_rol='Operador'
 and r.ucu_estado='Activo'
join public.evp_cta_cuenta c
  on c.cta_cuenta_id=r.ucu_cuenta_id
left join public.evp_uev_usuario_evento a
  on a.uev_usuario_id=u.usr_usuario_id
 and a.uev_cuenta_id=r.ucu_cuenta_id
 and a.uev_estado='Activo'
left join public.evp_eve_evento e
  on e.eve_cuenta_id=a.uev_cuenta_id
 and e.eve_evento_id=a.uev_evento_id
where u.usr_estado='Activo'
  and not u.usr_es_usuario_master
  and u.usr_usuario_auth_uuid is not null
order by c.cta_nombre_cuenta,u.usr_nombre_usuario,a.uev_evento_id;

-- G. REPRODUCCIÓN EXACTA DEL DISCOVERY C (OPERADORES CON ACCESO)
select
  u.usr_usuario_id as usuario_id,
  u.usr_nombre_usuario as nombre,
  u.usr_email as email,
  u.usr_usuario_auth_uuid as auth_uuid,
  r.ucu_cuenta_id as cuenta_id,
  c.cta_nombre_cuenta as cuenta,
  a.uev_evento_id as evento_id,
  e.eve_nombre_evento as evento
from public.evp_usr_usuario u
join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id
join public.evp_uev_usuario_evento a on a.uev_usuario_id=u.usr_usuario_id
 and a.uev_cuenta_id=r.ucu_cuenta_id
join public.evp_cta_cuenta c on c.cta_cuenta_id=r.ucu_cuenta_id
join public.evp_eve_evento e on e.eve_cuenta_id=a.uev_cuenta_id
 and e.eve_evento_id=a.uev_evento_id
where u.usr_estado='Activo' and not u.usr_es_usuario_master
  and u.usr_usuario_auth_uuid is not null
  and r.ucu_rol='Operador' and r.ucu_estado='Activo'
  and a.uev_estado='Activo' and c.cta_estado='Activo' and e.eve_estado='Activo'
order by c.cta_nombre_cuenta,e.eve_nombre_evento,u.usr_nombre_usuario;

-- H. CLASIFICACIÓN CORRECTA DE OPERATOR_ACCESS / OPERATOR_NO_ACCESS
-- NO_ACCESS exige UCU Operador/Activa en LA MISMA cuenta y ausencia global,
-- mediante NOT EXISTS, de UEV Activa para EL evento objetivo.
with operadores as (
  select u.usr_usuario_id,u.usr_nombre_usuario,u.usr_usuario_auth_uuid,
         r.ucu_cuenta_id
  from public.evp_usr_usuario u
  join public.evp_ucu_usuario_cuenta r
    on r.ucu_usuario_id=u.usr_usuario_id
   and r.ucu_rol='Operador' and r.ucu_estado='Activo'
  join public.evp_cta_cuenta c
    on c.cta_cuenta_id=r.ucu_cuenta_id and c.cta_estado='Activo'
  where u.usr_estado='Activo' and not u.usr_es_usuario_master
    and u.usr_usuario_auth_uuid is not null
), objetivos as (
  select e.eve_cuenta_id,e.eve_evento_id,e.eve_nombre_evento
  from public.evp_eve_evento e
  join public.evp_cta_cuenta c
    on c.cta_cuenta_id=e.eve_cuenta_id and c.cta_estado='Activo'
  where e.eve_estado='Activo'
)
select
  case when exists (
    select 1 from public.evp_uev_usuario_evento a
    where a.uev_usuario_id=o.usr_usuario_id
      and a.uev_cuenta_id=t.eve_cuenta_id
      and a.uev_evento_id=t.eve_evento_id
      and a.uev_estado='Activo'
  ) then 'OPERATOR_ACCESS' else 'OPERATOR_NO_ACCESS' end as caso,
  o.usr_usuario_id,o.usr_nombre_usuario as usuario,
  o.usr_usuario_auth_uuid as auth_uuid,
  t.eve_cuenta_id as cuenta_id,t.eve_evento_id as evento_id,
  t.eve_nombre_evento as evento
from operadores o
join objetivos t on t.eve_cuenta_id=o.ucu_cuenta_id
order by caso,o.usr_nombre_usuario,t.eve_cuenta_id,t.eve_evento_id;
