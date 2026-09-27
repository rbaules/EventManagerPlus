-- QR-1C-B1 fixture discovery: READ-ONLY. No crea ni modifica datos.
-- Seleccione una misma cuenta/evento TARGET con tres TARGET_INVITATION sin QR,
-- un ADMIN de esa cuenta y, si existen, los candidatos OTHER_* para rechazos.
WITH active_accounts AS (
    SELECT c.cta_cuenta_id
    FROM public.evp_cta_cuenta AS c
    WHERE c.cta_estado = 'Activo'
), active_events AS (
    SELECT e.eve_cuenta_id, e.eve_evento_id
    FROM public.evp_eve_evento AS e
    JOIN active_accounts AS a ON a.cta_cuenta_id = e.eve_cuenta_id
    WHERE e.eve_estado = 'Activo'
      AND e.eve_fase_evento IN ('Pre_evento', 'En_proceso')
      AND e.eve_fecha_hora_inicio IS NOT NULL
      AND e.eve_fecha_hora_fin > e.eve_fecha_hora_inicio
), target_invitations AS (
    SELECT i.inv_cuenta_id, i.inv_evento_id, i.inv_invitacion_id,
           pg_catalog.row_number() OVER (
               PARTITION BY i.inv_cuenta_id, i.inv_evento_id ORDER BY i.inv_invitacion_id
           ) AS candidate_number
    FROM public.evp_inv_invitacion AS i
    JOIN active_events AS e ON e.eve_cuenta_id = i.inv_cuenta_id
                         AND e.eve_evento_id = i.inv_evento_id
    WHERE i.inv_estado = 'Activo'
      AND NOT EXISTS (
          SELECT 1 FROM public.evp_iqr_invitacion_qr AS q
          WHERE q.iqr_cuenta_id = i.inv_cuenta_id
            AND q.iqr_evento_id = i.inv_evento_id
            AND q.iqr_invitacion_id = i.inv_invitacion_id
      )
)
SELECT 'MASTER' AS fixture_type, u.usr_usuario_auth_uuid::text AS auth_uuid,
       NULL::integer AS cuenta_id, NULL::integer AS evento_id, NULL::integer AS invitacion_id,
       'Master activo' AS detail
FROM public.evp_usr_usuario AS u
WHERE u.usr_estado = 'Activo' AND u.usr_es_usuario_master
UNION ALL
SELECT 'ACCOUNT_ROLE', u.usr_usuario_auth_uuid::text, r.ucu_cuenta_id, NULL, NULL,
       r.ucu_rol::text
FROM public.evp_usr_usuario AS u
JOIN public.evp_ucu_usuario_cuenta AS r ON r.ucu_usuario_id = u.usr_usuario_id
WHERE u.usr_estado = 'Activo' AND NOT u.usr_es_usuario_master
  AND r.ucu_estado = 'Activo' AND r.ucu_rol IN ('Administrador', 'Operador', 'Consulta')
UNION ALL
SELECT 'TARGET_EVENT', NULL, e.eve_cuenta_id, e.eve_evento_id, NULL,
       'Activo, fase y horario validos'
FROM active_events AS e
UNION ALL
SELECT 'TARGET_INVITATION', NULL, i.inv_cuenta_id, i.inv_evento_id, i.inv_invitacion_id,
       'Sin historial QR; usar tres del mismo evento'
FROM target_invitations AS i
WHERE i.candidate_number <= 10
UNION ALL
SELECT 'OTHER_ACCOUNT', NULL, a.cta_cuenta_id, NULL, NULL, 'Cuenta activa alternativa'
FROM active_accounts AS a
UNION ALL
SELECT 'OTHER_EVENT_SAME_ACCOUNT', NULL, e.eve_cuenta_id, e.eve_evento_id, NULL,
       'Evento activo alternativo; un Administrador de cuenta sigue autorizado por diseno'
FROM active_events AS e
UNION ALL
SELECT 'FOREIGN_INVITATION', NULL, i.inv_cuenta_id, i.inv_evento_id, i.inv_invitacion_id,
       'Invitacion activa alternativa'
FROM target_invitations AS i
UNION ALL
SELECT 'NO_ACCESS_USER', u.usr_usuario_auth_uuid::text, NULL, NULL, NULL,
       'Activo no Master; confirmar que no tiene UCU en la cuenta objetivo'
FROM public.evp_usr_usuario AS u
WHERE u.usr_estado = 'Activo' AND NOT u.usr_es_usuario_master
  AND NOT EXISTS (
      SELECT 1 FROM public.evp_ucu_usuario_cuenta AS r
      WHERE r.ucu_usuario_id = u.usr_usuario_id AND r.ucu_estado = 'Activo'
  )
ORDER BY fixture_type, cuenta_id NULLS LAST, evento_id NULLS LAST, invitacion_id NULLS LAST, auth_uuid NULLS LAST;
