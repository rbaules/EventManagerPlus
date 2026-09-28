-- QR-2B fixture discovery: READ-ONLY.
WITH eventos AS (
 SELECT c.cta_cuenta_id cuenta_id,e.eve_evento_id evento_id,e.eve_fecha_hora_inicio inicio,e.eve_fecha_hora_fin fin
 FROM public.evp_cta_cuenta c JOIN public.evp_eve_evento e ON e.eve_cuenta_id=c.cta_cuenta_id
 WHERE c.cta_estado='Activo' AND e.eve_estado='Activo' AND e.eve_fase_evento='En_proceso'
), grupos AS (
 SELECT i.inv_cuenta_id cuenta_id,i.inv_evento_id evento_id,i.inv_invitacion_id invitacion_id,
        count(*) FILTER (WHERE g.ivt_estado='Activo') activos,
        count(*) FILTER (WHERE g.ivt_estado='Activo' AND NOT g.ivt_llegada_confirmada) pendientes
 FROM public.evp_inv_invitacion i JOIN public.evp_ivt_invitado g ON g.ivt_cuenta_id=i.inv_cuenta_id AND g.ivt_evento_id=i.inv_evento_id AND g.ivt_invitacion_id=i.inv_invitacion_id
 WHERE i.inv_estado='Activo' GROUP BY 1,2,3
), fixtures AS (
 SELECT 'TARGET_EVENT'::text AS fixture_type,NULL::text AS auth_uuid,e.cuenta_id AS cuenta_id,e.evento_id AS evento_id,NULL::integer AS invitacion_id,NULL::integer AS invitado_id,
  'En_proceso; inicio='||e.inicio||'; fin='||e.fin||'; ventana_actual='||(now() BETWEEN e.inicio-interval '8 hours' AND e.fin+interval '4 hours') AS detail FROM eventos e
 UNION ALL SELECT 'TARGET_GROUP'::text,NULL::text,g.cuenta_id,g.evento_id,g.invitacion_id,NULL::integer,'activos='||g.activos||'; pendientes='||g.pendientes FROM grupos g JOIN eventos e ON (e.cuenta_id,e.evento_id)=(g.cuenta_id,g.evento_id) WHERE g.activos>=3
 UNION ALL SELECT 'OTHER_GUEST'::text,NULL::text,g.ivt_cuenta_id,g.ivt_evento_id,g.ivt_invitacion_id,g.ivt_invitado_id,'Invitado activo para rechazo cross-invitation' FROM public.evp_ivt_invitado g WHERE g.ivt_estado='Activo'
 UNION ALL SELECT 'OTHER_EVENT'::text,NULL::text,e.cuenta_id,e.evento_id,NULL::integer,NULL::integer,'Contexto alternativo activo En_proceso' FROM eventos e
 UNION ALL SELECT 'MASTER'::text,u.usr_usuario_auth_uuid::text,NULL::integer,NULL::integer,NULL::integer,NULL::integer,'Master activo' FROM public.evp_usr_usuario u WHERE u.usr_estado='Activo' AND u.usr_es_usuario_master
 UNION ALL SELECT 'ADMIN'::text,u.usr_usuario_auth_uuid::text,r.ucu_cuenta_id,NULL::integer,NULL::integer,NULL::integer,'Administrador UCU activo' FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Administrador'
 UNION ALL SELECT 'OPERATOR_UEV'::text,u.usr_usuario_auth_uuid::text,x.uev_cuenta_id,x.uev_evento_id,NULL::integer,NULL::integer,'Operador UCU/UEV activos' FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id JOIN public.evp_uev_usuario_evento x ON x.uev_usuario_id=u.usr_usuario_id AND x.uev_cuenta_id=r.ucu_cuenta_id WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Operador' AND x.uev_estado='Activo'
 UNION ALL SELECT 'CONSULTA_UEV'::text,u.usr_usuario_auth_uuid::text,x.uev_cuenta_id,x.uev_evento_id,NULL::integer,NULL::integer,'Consulta UCU/UEV activos' FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id JOIN public.evp_uev_usuario_evento x ON x.uev_usuario_id=u.usr_usuario_id AND x.uev_cuenta_id=r.ucu_cuenta_id WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Consulta' AND x.uev_estado='Activo'
 UNION ALL SELECT 'NO_ACCESS_USER'::text,u.usr_usuario_auth_uuid::text,NULL::integer,NULL::integer,NULL::integer,NULL::integer,'Activo no Master sin UCU activa; confirmar contra target' FROM public.evp_usr_usuario u WHERE u.usr_estado='Activo' AND NOT u.usr_es_usuario_master AND NOT EXISTS(SELECT 1 FROM public.evp_ucu_usuario_cuenta r WHERE r.ucu_usuario_id=u.usr_usuario_id AND r.ucu_estado='Activo')
)
SELECT fixture_type,auth_uuid,cuenta_id,evento_id,invitacion_id,invitado_id,detail
FROM fixtures
ORDER BY fixture_type,cuenta_id NULLS LAST,evento_id NULLS LAST,invitacion_id NULLS LAST,invitado_id NULLS LAST,auth_uuid NULLS LAST;
