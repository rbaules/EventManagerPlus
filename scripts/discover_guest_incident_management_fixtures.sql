-- Discovery estrictamente READ-ONLY para test_guest_incident_management_rpc.sql.
-- Contiene exclusivamente SELECT/CTE/subconsultas. No prepara ni modifica datos.

-- A. MASTER ACTIVOS
select u.usr_usuario_id as usuario_id, u.usr_nombre_usuario as nombre,
       u.usr_email as email, u.usr_usuario_auth_uuid as auth_uuid
from public.evp_usr_usuario u
where u.usr_es_usuario_master and u.usr_estado='Activo'
  and u.usr_usuario_auth_uuid is not null
order by u.usr_nombre_usuario;

-- B. ADMINISTRADORES ACTIVOS EN CUENTAS ACTIVAS
select u.usr_usuario_id as usuario_id, u.usr_nombre_usuario as nombre,
       u.usr_email as email, u.usr_usuario_auth_uuid as auth_uuid,
       r.ucu_cuenta_id as cuenta_id, c.cta_nombre_cuenta as nombre_cuenta
from public.evp_usr_usuario u
join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id
join public.evp_cta_cuenta c on c.cta_cuenta_id=r.ucu_cuenta_id
where u.usr_estado='Activo' and not u.usr_es_usuario_master
  and u.usr_usuario_auth_uuid is not null
  and r.ucu_rol='Administrador' and r.ucu_estado='Activo'
  and c.cta_estado='Activo'
order by c.cta_nombre_cuenta,u.usr_nombre_usuario;

-- C. OPERADORES CON UCU+UEV ACTIVAS EN CUENTA/EVENTO ACTIVOS
select u.usr_usuario_id as usuario_id, u.usr_nombre_usuario as nombre,
       u.usr_email as email, u.usr_usuario_auth_uuid as auth_uuid,
       r.ucu_cuenta_id as cuenta_id, c.cta_nombre_cuenta as cuenta,
       a.uev_evento_id as evento_id, e.eve_nombre_evento as evento
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

-- D. CONSULTA CON UCU+UEV ACTIVAS EN CUENTA/EVENTO ACTIVOS
select u.usr_usuario_id as usuario_id, u.usr_nombre_usuario as nombre,
       u.usr_email as email, u.usr_usuario_auth_uuid as auth_uuid,
       r.ucu_cuenta_id as cuenta_id, c.cta_nombre_cuenta as cuenta,
       a.uev_evento_id as evento_id, e.eve_nombre_evento as evento
from public.evp_usr_usuario u
join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id
join public.evp_uev_usuario_evento a on a.uev_usuario_id=u.usr_usuario_id
 and a.uev_cuenta_id=r.ucu_cuenta_id
join public.evp_cta_cuenta c on c.cta_cuenta_id=r.ucu_cuenta_id
join public.evp_eve_evento e on e.eve_cuenta_id=a.uev_cuenta_id
 and e.eve_evento_id=a.uev_evento_id
where u.usr_estado='Activo' and not u.usr_es_usuario_master
  and u.usr_usuario_auth_uuid is not null
  and r.ucu_rol='Consulta' and r.ucu_estado='Activo'
  and a.uev_estado='Activo' and c.cta_estado='Activo' and e.eve_estado='Activo'
order by c.cta_nombre_cuenta,e.eve_nombre_evento,u.usr_nombre_usuario;

-- E. INVITADOS EN CUENTA/EVENTO ACTIVOS
select i.ivt_invitado_uuid, i.ivt_nombre_invitado as nombre_invitado,
       i.ivt_cuenta_id as cuenta_id, c.cta_nombre_cuenta as cuenta,
       i.ivt_evento_id as evento_id, e.eve_nombre_evento as evento,
       i.ivt_tiene_novedad, i.ivt_descripcion_novedad,
       i.ivt_novedad_creada, i.ivt_novedad_creada_por,
       i.ivt_novedad_mod, i.ivt_novedad_mod_por
from public.evp_ivt_invitado i
join public.evp_eve_evento e on e.eve_cuenta_id=i.ivt_cuenta_id
 and e.eve_evento_id=i.ivt_evento_id
join public.evp_cta_cuenta c on c.cta_cuenta_id=e.eve_cuenta_id
where c.cta_estado='Activo' and e.eve_estado='Activo'
order by case when lower(i.ivt_nombre_invitado) like '%test%' then 0 else 1 end,
         c.cta_nombre_cuenta,e.eve_nombre_evento,i.ivt_nombre_invitado;

-- F. CRUCES LISTOS: Master/Admin/Operador/Consulta con evento escribible.
with actores as (
  select u.usr_usuario_id,u.usr_nombre_usuario,u.usr_usuario_auth_uuid,
         u.usr_es_usuario_master,r.ucu_rol,r.ucu_cuenta_id,a.uev_evento_id
  from public.evp_usr_usuario u
  left join public.evp_ucu_usuario_cuenta r on r.ucu_usuario_id=u.usr_usuario_id and r.ucu_estado='Activo'
  left join public.evp_uev_usuario_evento a on a.uev_usuario_id=u.usr_usuario_id
   and a.uev_cuenta_id=r.ucu_cuenta_id and a.uev_estado='Activo'
  where u.usr_estado='Activo' and u.usr_usuario_auth_uuid is not null
), targets as (
  select i.ivt_invitado_uuid,i.ivt_nombre_invitado,i.ivt_cuenta_id,i.ivt_evento_id,
         c.cta_nombre_cuenta,e.eve_nombre_evento,e.eve_fase_evento
  from public.evp_ivt_invitado i
  join public.evp_eve_evento e on e.eve_cuenta_id=i.ivt_cuenta_id and e.eve_evento_id=i.ivt_evento_id
  join public.evp_cta_cuenta c on c.cta_cuenta_id=e.eve_cuenta_id
  where c.cta_estado='Activo' and e.eve_estado='Activo'
    and e.eve_fase_evento in ('Pre_evento','En_proceso')
)
select case
         when a.usr_es_usuario_master then 'MASTER_ACCESS'
         when a.ucu_rol='Administrador' and a.ucu_cuenta_id=t.ivt_cuenta_id then 'ADMIN_ACCESS'
         when a.ucu_rol='Administrador' and a.ucu_cuenta_id<>t.ivt_cuenta_id then 'ADMIN_NO_ACCESS'
         when a.ucu_rol='Operador' and a.ucu_cuenta_id=t.ivt_cuenta_id and a.uev_evento_id=t.ivt_evento_id then 'OPERATOR_ACCESS'
         when a.ucu_rol='Operador' then 'OPERATOR_NO_ACCESS'
         when a.ucu_rol='Consulta' and a.ucu_cuenta_id=t.ivt_cuenta_id and a.uev_evento_id=t.ivt_evento_id then 'CONSULTA_READ_ONLY'
       end as caso,
       a.usr_usuario_id,a.usr_nombre_usuario,a.usr_usuario_auth_uuid as auth_uuid,
       t.ivt_invitado_uuid,t.ivt_nombre_invitado,t.ivt_cuenta_id,t.cta_nombre_cuenta,
       t.ivt_evento_id,t.eve_nombre_evento,t.eve_fase_evento
from actores a cross join targets t
where a.usr_es_usuario_master
   or (a.ucu_rol='Administrador' and a.ucu_cuenta_id=t.ivt_cuenta_id)
   or (a.ucu_rol='Administrador' and a.ucu_cuenta_id<>t.ivt_cuenta_id)
   or (a.ucu_rol='Operador' and (a.ucu_cuenta_id<>t.ivt_cuenta_id or a.uev_evento_id is distinct from t.ivt_evento_id))
   or (a.ucu_rol='Operador' and a.ucu_cuenta_id=t.ivt_cuenta_id and a.uev_evento_id=t.ivt_evento_id)
   or (a.ucu_rol='Consulta' and a.ucu_cuenta_id=t.ivt_cuenta_id and a.uev_evento_id=t.ivt_evento_id)
order by caso,a.usr_nombre_usuario,t.cta_nombre_cuenta,t.eve_nombre_evento;

-- G. FASES DISPONIBLES. Resultado vacío para una fase significa que no existe fixture actual.
select e.eve_cuenta_id as cuenta_id,e.eve_evento_id as evento_id,
       e.eve_nombre_evento as nombre,e.eve_fase_evento as fase,e.eve_estado as estado
from public.evp_eve_evento e
where e.eve_fase_evento in ('Pre_evento','En_proceso','Post_evento','Cerrado')
order by e.eve_fase_evento,e.eve_cuenta_id,e.eve_evento_id;
