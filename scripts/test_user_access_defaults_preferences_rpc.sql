-- Verificación local posterior a 202608100001. Este archivo NO aplica la migración.

-- ============================================================================
-- A. PRUEBAS SEGURAS / READ ONLY
-- Ejecutadas únicamente cuando este archivo se corre explícitamente en una DB.
-- ============================================================================
do $$
declare
  n text;
  p record;
  trusted_owners constant text[] := array['postgres','supabase_admin'];
  business_functions constant text[] := array[
    'public.evp_admin_crear_usuario(text,text,text,integer,integer)',
    'public.evp_admin_actualizar_usuario(uuid,text,text)',
    'public.evp_admin_cambiar_rol_cuenta(uuid,integer,text)',
    'public.evp_admin_cambiar_estado_cuenta(uuid,integer,text)',
    'public.evp_usuario_actualizar_preferencias(integer,integer)',
    'public.evp_admin_cambiar_estado_usuario(uuid,text)'
  ];
  private_helpers constant text[] := array[
    'public.evp_priv_usuario_tiene_acceso(uuid,integer,integer)',
    'public.evp_priv_usuario_puede_tener_default(uuid,integer,integer)',
    'public.evp_priv_limpiar_defaults(uuid)'
  ];
begin
  foreach n in array business_functions || private_helpers loop
    if to_regprocedure(n) is null then raise exception 'Falta función %',n; end if;
    select pr.prosecdef,pr.proconfig,pr.proacl,pr.proowner,
           pg_get_userbyid(pr.proowner) owner_name
      into p from pg_proc pr where pr.oid=to_regprocedure(n);
    if not p.prosecdef then raise exception '% no es SECURITY DEFINER',n; end if;
    if not (p.proconfig @> array['search_path=""']::text[]) then
      raise exception '% no tiene search_path vacío: %',n,p.proconfig;
    end if;
    if not (p.owner_name=any(trusted_owners)) then
      raise exception '% tiene propietario no confiable: %',n,p.owner_name;
    end if;
    if has_function_privilege('anon',n,'execute') then raise exception 'anon conserva EXECUTE en %',n; end if;
    if exists(select 1 from aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where a.grantee=0 and a.privilege_type='EXECUTE') then
      raise exception 'PUBLIC conserva EXECUTE en %',n;
    end if;
  end loop;

  foreach n in array business_functions loop
    if not has_function_privilege('authenticated',n,'execute') then
      raise exception 'authenticated no tiene EXECUTE en %',n;
    end if;
  end loop;
  foreach n in array private_helpers loop
    if has_function_privilege('authenticated',n,'execute') then
      raise exception 'authenticated conserva EXECUTE en helper %',n;
    end if;
  end loop;

  if exists (
    select 1 from pg_proc pr join pg_namespace ns on ns.oid=pr.pronamespace
    where ns.nspname='public' and pr.proname='evp_admin_crear_usuario'
      and pg_get_function_identity_arguments(pr.oid)<>'p_nombre text, p_email text, p_rol text, p_cuenta_id integer, p_evento_id integer'
      and has_function_privilege('authenticated',pr.oid,'execute')
  ) then raise exception 'authenticated puede ejecutar una firma obsoleta de evp_admin_crear_usuario'; end if;
end $$;

-- Semántica estática esperada, complementada por las pruebas Python locales:
-- acceso efectivo exige Activo; elegibilidad admite Activo/Preregistrado;
-- Preferencias consulta acceso efectivo; limpieza consulta elegibilidad.

-- ============================================================================
-- B. PRUEBAS QUE ESCRIBEN (DOCUMENTADAS, NO EJECUTADAS POR ESTE ARCHIVO)
-- En una transacción descartable: crear preregistrados por los cuatro roles,
-- cambiar UCU, verificar limpieza de defaults y que UEV permanece almacenada.
-- ============================================================================

-- ============================================================================
-- C. PRUEBAS CON JWT REALES (DOCUMENTADAS, NO EJECUTADAS POR ESTE ARCHIVO)
-- Probar Master, Administrador, Operador y Consulta. Confirmar que Preferencias
-- rechaza Preregistrado/inactivo y que cada rol solo elige contextos permitidos.
-- ============================================================================

-- ============================================================================
-- D. PRUEBAS DE CONCURRENCIA (DOCUMENTADAS, NO EJECUTADAS POR ESTE ARCHIVO)
-- En dos sesiones: cambio simultáneo de la misma UCU/default, inactivación del
-- último Master y creación concurrente con el mismo correo.
-- ============================================================================
