-- QR-2A fixture discovery: READ-ONLY. No crea ni modifica datos.
-- Seleccione un TARGET_EVENT En_proceso y QR_ACTIVE del mismo contexto.
WITH eligible_events AS (
    SELECT c.cta_cuenta_id, e.eve_evento_id, e.eve_fecha_hora_inicio, e.eve_fecha_hora_fin
    FROM public.evp_cta_cuenta c JOIN public.evp_eve_evento e ON e.eve_cuenta_id=c.cta_cuenta_id
    WHERE c.cta_estado='Activo' AND e.eve_estado='Activo' AND e.eve_fase_evento='En_proceso'
), active_qr AS (
    SELECT q.iqr_cuenta_id,q.iqr_evento_id,q.iqr_invitacion_id,q.iqr_codigo
    FROM public.evp_iqr_invitacion_qr q JOIN eligible_events e ON e.cta_cuenta_id=q.iqr_cuenta_id AND e.eve_evento_id=q.iqr_evento_id
    JOIN public.evp_inv_invitacion i ON i.inv_cuenta_id=q.iqr_cuenta_id AND i.inv_evento_id=q.iqr_evento_id AND i.inv_invitacion_id=q.iqr_invitacion_id
    WHERE q.iqr_estado='Activo' AND q.iqr_fecha_revocacion IS NULL AND q.iqr_valido_desde<=pg_catalog.now() AND q.iqr_valido_hasta>=pg_catalog.now() AND i.inv_estado='Activo'
), revoked_qr AS (
    SELECT q.iqr_cuenta_id,q.iqr_evento_id,q.iqr_invitacion_id,q.iqr_codigo FROM public.evp_iqr_invitacion_qr q
    JOIN eligible_events e ON e.cta_cuenta_id=q.iqr_cuenta_id AND e.eve_evento_id=q.iqr_evento_id
    WHERE q.iqr_estado='Revocado'
)
SELECT 'MASTER' fixture_type,u.usr_usuario_auth_uuid::text auth_uuid,NULL::integer cuenta_id,NULL::integer evento_id,NULL::integer invitacion_id,NULL::text codigo,'Master activo' detail
FROM public.evp_usr_usuario u WHERE u.usr_estado='Activo' AND u.usr_es_usuario_master
UNION ALL
SELECT 'ADMIN',u.usr_usuario_auth_uuid::text,r.ucu_cuenta_id,NULL,NULL,NULL,'Administrador UCU activo'
FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Administrador'
UNION ALL
SELECT 'OPERATOR_UEV',u.usr_usuario_auth_uuid::text,e.cta_cuenta_id,e.eve_evento_id,NULL,NULL,'Operador con UCU y UEV activos'
FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id JOIN public.evp_uev_usuario_evento x ON x.uev_usuario_id=u.usr_usuario_id AND x.uev_cuenta_id=r.ucu_cuenta_id JOIN eligible_events e ON e.cta_cuenta_id=x.uev_cuenta_id AND e.eve_evento_id=x.uev_evento_id
WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Operador' AND x.uev_estado='Activo'
UNION ALL
SELECT 'CONSULTA_UEV',u.usr_usuario_auth_uuid::text,e.cta_cuenta_id,e.eve_evento_id,NULL,NULL,'Consulta con UCU y UEV activos'
FROM public.evp_usr_usuario u JOIN public.evp_ucu_usuario_cuenta r ON r.ucu_usuario_id=u.usr_usuario_id JOIN public.evp_uev_usuario_evento x ON x.uev_usuario_id=u.usr_usuario_id AND x.uev_cuenta_id=r.ucu_cuenta_id JOIN eligible_events e ON e.cta_cuenta_id=x.uev_cuenta_id AND e.eve_evento_id=x.uev_evento_id
WHERE u.usr_estado='Activo' AND r.ucu_estado='Activo' AND r.ucu_rol='Consulta' AND x.uev_estado='Activo'
UNION ALL SELECT CASE WHEN pg_catalog.now() BETWEEN eve_fecha_hora_inicio-pg_catalog.make_interval(hours=>8) AND eve_fecha_hora_fin+pg_catalog.make_interval(hours=>4) THEN 'TARGET_EVENT_WINDOW_CURRENT' ELSE 'TARGET_EVENT_WINDOW_EXPIRED' END,NULL,cta_cuenta_id,eve_evento_id,NULL,NULL,CASE WHEN pg_catalog.now() BETWEEN eve_fecha_hora_inicio-pg_catalog.make_interval(hours=>8) AND eve_fecha_hora_fin+pg_catalog.make_interval(hours=>4) THEN 'Activo En_proceso; ventana QR incluye ahora' ELSE 'Activo En_proceso; ventana QR no incluye ahora' END FROM eligible_events
UNION ALL SELECT 'QR_ACTIVE',NULL,iqr_cuenta_id,iqr_evento_id,iqr_invitacion_id,iqr_codigo,'Activo y vigente' FROM active_qr
UNION ALL SELECT 'QR_REVOKED',NULL,iqr_cuenta_id,iqr_evento_id,iqr_invitacion_id,iqr_codigo,'Revocado' FROM revoked_qr
UNION ALL SELECT 'OTHER_QR_CONTEXT',NULL,iqr_cuenta_id,iqr_evento_id,iqr_invitacion_id,iqr_codigo,'Usar fuera de su cuenta/evento' FROM active_qr
UNION ALL
SELECT 'NO_ACCESS_USER',u.usr_usuario_auth_uuid::text,NULL,NULL,NULL,NULL,'Activo no Master; verificar contra TARGET elegido'
FROM public.evp_usr_usuario u WHERE u.usr_estado='Activo' AND NOT u.usr_es_usuario_master
ORDER BY fixture_type,cuenta_id NULLS LAST,evento_id NULLS LAST,invitacion_id NULLS LAST,auth_uuid NULLS LAST;
