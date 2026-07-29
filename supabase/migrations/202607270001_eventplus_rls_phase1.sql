-- PROPUESTA NO EJECUTADA - EventPlus RLS fase 1.
-- Requiere validar primero scripts/supabase_rls_diagnostics.sql.
-- Diseñada para public y para JWT de Supabase (auth.uid()).

begin;

-- Helpers SECURITY DEFINER: deben leer tablas protegidas sin recursión RLS.
-- No aceptan identidad/rol desde el cliente y fijan search_path.
create or replace function public.evp_rls_usuario_id()
returns uuid language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select u.usr_usuario_id
  from public.evp_usr_usuario u
  where u.usr_usuario_auth_uuid = auth.uid() and u.usr_estado = 'Activo'
  limit 1
$$;

create or replace function public.evp_rls_es_master()
returns boolean language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select coalesce((
    select u.usr_es_usuario_master
    from public.evp_usr_usuario u
    where u.usr_usuario_auth_uuid = auth.uid() and u.usr_estado = 'Activo'
    limit 1
  ), false)
$$;

create or replace function public.evp_rls_rol_cuenta(p_cuenta_id integer)
returns text language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select case when public.evp_rls_es_master() then 'Master'
    else (
      select uc.ucu_rol from public.evp_ucu_usuario_cuenta uc
      where uc.ucu_usuario_id = public.evp_rls_usuario_id()
        and uc.ucu_cuenta_id = p_cuenta_id and uc.ucu_estado = 'Activo'
      limit 1
    ) end
$$;

create or replace function public.evp_rls_tiene_cuenta(p_cuenta_id integer)
returns boolean language sql stable security definer
set search_path = pg_catalog, public, auth
as $$ select public.evp_rls_rol_cuenta(p_cuenta_id) is not null $$;

create or replace function public.evp_rls_tiene_evento(
  p_cuenta_id integer, p_evento_id integer
) returns boolean language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select coalesce(
    exists (
      select 1 from public.evp_eve_evento e
      where e.eve_cuenta_id = p_cuenta_id and e.eve_evento_id = p_evento_id
        and e.eve_estado = 'Activo'
        and (
          public.evp_rls_rol_cuenta(p_cuenta_id) in ('Master','Administrador')
          or (
            public.evp_rls_rol_cuenta(p_cuenta_id) in ('Operador','Consulta')
            and exists (
              select 1 from public.evp_uev_usuario_evento ue
              where ue.uev_cuenta_id = p_cuenta_id
                and ue.uev_evento_id = p_evento_id
                and ue.uev_usuario_id = public.evp_rls_usuario_id()
                and ue.uev_estado = 'Activo'
            )
          )
        )
    ), false)
$$;

create or replace function public.evp_rls_puede_administrar_evento(
  p_cuenta_id integer, p_evento_id integer
) returns boolean language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select public.evp_rls_tiene_evento(p_cuenta_id, p_evento_id)
     and public.evp_rls_rol_cuenta(p_cuenta_id) in ('Master','Administrador')
$$;

create or replace function public.evp_rls_puede_operar_evento(
  p_cuenta_id integer, p_evento_id integer
) returns boolean language sql stable security definer
set search_path = pg_catalog, public, auth
as $$
  select public.evp_rls_tiene_evento(p_cuenta_id, p_evento_id)
     and public.evp_rls_rol_cuenta(p_cuenta_id) in ('Master','Administrador','Operador')
     and exists (
       select 1 from public.evp_eve_evento e
       where e.eve_cuenta_id = p_cuenta_id and e.eve_evento_id = p_evento_id
         and e.eve_estado = 'Activo' and e.eve_fase_evento = 'En_proceso'
     )
$$;

revoke all on function public.evp_rls_usuario_id() from public, anon;
revoke all on function public.evp_rls_es_master() from public, anon;
revoke all on function public.evp_rls_rol_cuenta(integer) from public, anon;
revoke all on function public.evp_rls_tiene_cuenta(integer) from public, anon;
revoke all on function public.evp_rls_tiene_evento(integer, integer) from public, anon;
revoke all on function public.evp_rls_puede_administrar_evento(integer, integer) from public, anon;
revoke all on function public.evp_rls_puede_operar_evento(integer, integer) from public, anon;
grant execute on function public.evp_rls_usuario_id() to authenticated;
grant execute on function public.evp_rls_es_master() to authenticated;
grant execute on function public.evp_rls_rol_cuenta(integer) to authenticated;
grant execute on function public.evp_rls_tiene_cuenta(integer) to authenticated;
grant execute on function public.evp_rls_tiene_evento(integer, integer) to authenticated;
grant execute on function public.evp_rls_puede_administrar_evento(integer, integer) to authenticated;
grant execute on function public.evp_rls_puede_operar_evento(integer, integer) to authenticated;

alter table public.evp_usr_usuario enable row level security;
alter table public.evp_ucu_usuario_cuenta enable row level security;
alter table public.evp_uev_usuario_evento enable row level security;
alter table public.evp_cta_cuenta enable row level security;
alter table public.evp_lug_lugar enable row level security;
alter table public.evp_sal_salon enable row level security;
alter table public.evp_eve_evento enable row level security;
alter table public.evp_mes_mesa enable row level security;
alter table public.evp_inv_invitacion enable row level security;
alter table public.evp_ivt_invitado enable row level security;
alter table public.evp_pai_pais enable row level security;

-- Re-ejecutable: elimina solamente políticas propiedad de esta propuesta.
drop policy if exists evp_rls_usr_select on public.evp_usr_usuario;
create policy evp_rls_usr_select on public.evp_usr_usuario for select to authenticated
using (usr_usuario_auth_uuid = auth.uid() or public.evp_rls_es_master());

drop policy if exists evp_rls_ucu_select on public.evp_ucu_usuario_cuenta;
create policy evp_rls_ucu_select on public.evp_ucu_usuario_cuenta for select to authenticated
using (ucu_usuario_id = public.evp_rls_usuario_id()
       or public.evp_rls_rol_cuenta(ucu_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_ucu_insert on public.evp_ucu_usuario_cuenta;
create policy evp_rls_ucu_insert on public.evp_ucu_usuario_cuenta for insert to authenticated
with check (public.evp_rls_rol_cuenta(ucu_cuenta_id) in ('Master','Administrador')
            and ucu_rol in ('Administrador','Operador','Consulta'));
drop policy if exists evp_rls_ucu_update on public.evp_ucu_usuario_cuenta;
create policy evp_rls_ucu_update on public.evp_ucu_usuario_cuenta for update to authenticated
using (public.evp_rls_rol_cuenta(ucu_cuenta_id) in ('Master','Administrador'))
with check (public.evp_rls_rol_cuenta(ucu_cuenta_id) in ('Master','Administrador')
            and ucu_rol in ('Administrador','Operador','Consulta'));
drop policy if exists evp_rls_ucu_delete on public.evp_ucu_usuario_cuenta;
create policy evp_rls_ucu_delete on public.evp_ucu_usuario_cuenta for delete to authenticated
using (public.evp_rls_rol_cuenta(ucu_cuenta_id) in ('Master','Administrador')
       and ucu_usuario_id <> public.evp_rls_usuario_id());

drop policy if exists evp_rls_uev_select on public.evp_uev_usuario_evento;
create policy evp_rls_uev_select on public.evp_uev_usuario_evento for select to authenticated
using (uev_usuario_id = public.evp_rls_usuario_id()
       or public.evp_rls_rol_cuenta(uev_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_uev_insert on public.evp_uev_usuario_evento;
create policy evp_rls_uev_insert on public.evp_uev_usuario_evento for insert to authenticated
with check (public.evp_rls_rol_cuenta(uev_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_uev_update on public.evp_uev_usuario_evento;
create policy evp_rls_uev_update on public.evp_uev_usuario_evento for update to authenticated
using (public.evp_rls_rol_cuenta(uev_cuenta_id) in ('Master','Administrador'))
with check (public.evp_rls_rol_cuenta(uev_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_uev_delete on public.evp_uev_usuario_evento;
create policy evp_rls_uev_delete on public.evp_uev_usuario_evento for delete to authenticated
using (public.evp_rls_rol_cuenta(uev_cuenta_id) in ('Master','Administrador'));

drop policy if exists evp_rls_cta_select on public.evp_cta_cuenta;
create policy evp_rls_cta_select on public.evp_cta_cuenta for select to authenticated
using (public.evp_rls_tiene_cuenta(cta_cuenta_id));
drop policy if exists evp_rls_cta_update on public.evp_cta_cuenta;
create policy evp_rls_cta_update on public.evp_cta_cuenta for update to authenticated
using (public.evp_rls_es_master()) with check (public.evp_rls_es_master());

drop policy if exists evp_rls_eve_select on public.evp_eve_evento;
create policy evp_rls_eve_select on public.evp_eve_evento for select to authenticated
using (public.evp_rls_tiene_evento(eve_cuenta_id, eve_evento_id));
drop policy if exists evp_rls_eve_insert on public.evp_eve_evento;
create policy evp_rls_eve_insert on public.evp_eve_evento for insert to authenticated
with check (public.evp_rls_rol_cuenta(eve_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_eve_update on public.evp_eve_evento;
create policy evp_rls_eve_update on public.evp_eve_evento for update to authenticated
using (public.evp_rls_puede_administrar_evento(eve_cuenta_id, eve_evento_id))
with check (public.evp_rls_puede_administrar_evento(eve_cuenta_id, eve_evento_id));
drop policy if exists evp_rls_eve_delete on public.evp_eve_evento;
create policy evp_rls_eve_delete on public.evp_eve_evento for delete to authenticated
using (public.evp_rls_es_master());

-- Tablas con cuenta.
drop policy if exists evp_rls_lug_all on public.evp_lug_lugar;
create policy evp_rls_lug_all on public.evp_lug_lugar for all to authenticated
using (public.evp_rls_tiene_cuenta(lug_cuenta_id))
with check (public.evp_rls_rol_cuenta(lug_cuenta_id) in ('Master','Administrador'));
drop policy if exists evp_rls_sal_all on public.evp_sal_salon;
create policy evp_rls_sal_all on public.evp_sal_salon for all to authenticated
using (public.evp_rls_tiene_cuenta(sal_cuenta_id))
with check (public.evp_rls_rol_cuenta(sal_cuenta_id) in ('Master','Administrador'));

-- Tablas con evento.
drop policy if exists evp_rls_mes_all on public.evp_mes_mesa;
create policy evp_rls_mes_all on public.evp_mes_mesa for all to authenticated
using (public.evp_rls_tiene_evento(mes_cuenta_id, mes_evento_id))
with check (public.evp_rls_puede_administrar_evento(mes_cuenta_id, mes_evento_id));
drop policy if exists evp_rls_inv_select on public.evp_inv_invitacion;
create policy evp_rls_inv_select on public.evp_inv_invitacion for select to authenticated
using (public.evp_rls_tiene_evento(inv_cuenta_id, inv_evento_id));
drop policy if exists evp_rls_inv_mutate on public.evp_inv_invitacion;
create policy evp_rls_inv_mutate on public.evp_inv_invitacion for all to authenticated
using (public.evp_rls_puede_administrar_evento(inv_cuenta_id, inv_evento_id))
with check (public.evp_rls_puede_administrar_evento(inv_cuenta_id, inv_evento_id));
drop policy if exists evp_rls_ivt_select on public.evp_ivt_invitado;
create policy evp_rls_ivt_select on public.evp_ivt_invitado for select to authenticated
using (public.evp_rls_tiene_evento(ivt_cuenta_id, ivt_evento_id));
drop policy if exists evp_rls_ivt_insert_admin on public.evp_ivt_invitado;
create policy evp_rls_ivt_insert_admin on public.evp_ivt_invitado for insert to authenticated
with check (public.evp_rls_puede_administrar_evento(ivt_cuenta_id, ivt_evento_id));
drop policy if exists evp_rls_ivt_update_admin on public.evp_ivt_invitado;
create policy evp_rls_ivt_update_admin on public.evp_ivt_invitado for update to authenticated
using (public.evp_rls_puede_administrar_evento(ivt_cuenta_id, ivt_evento_id))
with check (public.evp_rls_puede_administrar_evento(ivt_cuenta_id, ivt_evento_id));
drop policy if exists evp_rls_ivt_delete on public.evp_ivt_invitado;
create policy evp_rls_ivt_delete on public.evp_ivt_invitado for delete to authenticated
using (public.evp_rls_es_master());

-- Catálogo autenticado. El USING true queda limitado y justificado a países.
drop policy if exists evp_rls_pai_select on public.evp_pai_pais;
create policy evp_rls_pai_select on public.evp_pai_pais for select to authenticated using (true);

revoke all on all tables in schema public from anon;
revoke insert, update, delete on public.evp_usr_usuario from authenticated;
revoke insert, update, delete on public.evp_cta_cuenta from authenticated;
revoke insert, update, delete on public.evp_ivt_invitado from authenticated;
grant select on public.evp_usr_usuario, public.evp_ucu_usuario_cuenta,
  public.evp_uev_usuario_evento, public.evp_cta_cuenta, public.evp_lug_lugar,
  public.evp_sal_salon, public.evp_eve_evento, public.evp_mes_mesa,
  public.evp_inv_invitacion, public.evp_ivt_invitado, public.evp_pai_pais
to authenticated;
-- Las mutaciones de invitado quedan revocadas hasta instalar RPC transaccionales.

-- Verificación manual posterior (NO ejecutar en esta tarea):
-- select * from pg_policies where schemaname='public' order by tablename, policyname;
-- select relname, relrowsecurity from pg_class where relnamespace='public'::regnamespace;
commit;
