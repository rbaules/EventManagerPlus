# Android Test Checklist - EventPlus Check-in

## Dispositivos

- [ ] Telefono vertical.
- [ ] Telefono horizontal.
- [ ] Tablet vertical.
- [ ] Tablet horizontal.

## Roles

- [ ] Master.
- [ ] Administrador.
- [ ] Operador.
- [ ] Consulta: solo eventos asignados, navegación y detalle sin mutaciones.

## OAuth

- [ ] Login abre navegador.
- [ ] Google autentica.
- [ ] Supabase acepta redirect.
- [ ] Deep link vuelve al APK.
- [ ] No se procesa dos veces el callback.

## Contexto

- [ ] Cuentas autorizadas correctas.
- [ ] Eventos autorizados correctos.
- [ ] Entra a Registrar llegadas.
- [ ] Cambiar cuenta/evento limpia busquedas anteriores.

## Invitados

- [ ] Buscar por invitado.
- [ ] Buscar por mesa.
- [ ] Limpiar busqueda.
- [ ] Paginacion.
- [ ] Detalle solo lectura.
- [ ] No aparecen crear/editar/eliminar en Check-in.

## Llegadas

- [ ] Buscar invitado.
- [ ] Cargar invitacion completa.
- [ ] Seleccionar pendientes.
- [ ] Confirmar multiples.
- [ ] Revertir llegada.
- [ ] Contadores se actualizan.

## Fases

- [ ] Pre_evento: consulta si, llegadas no.
- [ ] En_proceso: consulta si, confirmar/revertir si autorizado.
- [ ] Post_evento: consulta si, llegadas no.

## Conectividad

- [ ] Wi-Fi.
- [ ] Datos moviles.
- [ ] Perdida temporal de conexion.
- [ ] Reintento sin duplicados.

## Ciclo de vida

- [ ] Minimizar/restaurar.
- [ ] Bloquear/desbloquear pantalla.
- [ ] Cambiar orientacion.
- [ ] Regresar desde navegador.
- [ ] Logout limpia contexto.

## Dos dispositivos

- [ ] Ambos abren mismo evento.
- [ ] Ambos buscan misma invitacion.
- [ ] Dispositivo A confirma integrante.
- [ ] Dispositivo B intenta confirmar el mismo integrante.
- [ ] No hay duplicado y se refresca estado.
- [ ] Se prueba reversion desde uno de los dispositivos.
