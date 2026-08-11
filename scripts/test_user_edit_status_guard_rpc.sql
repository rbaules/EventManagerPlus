-- Ejecutar solo en un entorno controlado despues de aplicar 202608110002.
-- Este archivo no aplica migraciones y descarta toda escritura.

do $$
declare d text;
begin
  if to_regprocedure('public.evp_admin_actualizar_usuario(uuid,text,text)') is null then
    raise exception 'Falta evp_admin_actualizar_usuario(uuid,text,text)';
  end if;
  select lower(pg_get_functiondef('public.evp_admin_actualizar_usuario(uuid,text,text)'::regprocedure)) into d;
  if position('usr_estadonotin(''activo'',''preregistrado'')' in replace(d,' ',''))=0 then
    raise exception 'La RPC no contiene guard Activo/Preregistrado';
  end if;
  if position('user_edit_invalid_status' in d)=0 then raise exception 'Falta USER_EDIT_INVALID_STATUS'; end if;
end $$;

-- Prueba funcional con JWT Master real y datos de staging:
-- BEGIN;
--   1. set_config('request.jwt.claim.sub','<AUTH_UUID_MASTER>',true).
--   2. llamar evp_admin_actualizar_usuario sobre objetivo Inactivo;
--      esperado: USER_EDIT_INVALID_STATUS y datos sin cambios.
--   3. repetir sobre objetivo Suspendido; mismo resultado.
--   4. llamar sobre objetivos Activo y Preregistrado; esperado OK.
--   5. repetir Activo/Preregistrado con JWT Administrador y UCU compartida válida.
-- ROLLBACK;
