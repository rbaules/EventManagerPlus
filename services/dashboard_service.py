from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.authorization_service import puede_consultar
from services.evento_context_service import evento_key
from services.response_utils import extract_data, safe_get, to_dict


@dataclass(frozen=True)
class IntervaloLlegadas:
    inicio: datetime
    final: datetime
    etiqueta: str
    cantidad: int = 0


@dataclass(frozen=True)
class IndicadoresDashboard:
    total_invitados: int = 0
    invitados_llegaron: int = 0
    invitados_pendientes: int = 0
    porcentaje_llegadas: float = 0.0
    porcentaje_pendientes: float = 0.0
    total_mesas: int = 0
    mesas_con_invitados: int = 0
    mesas_completas: int = 0
    mesas_pendientes: int = 0
    mesas_parciales: int = 0
    mesas_sin_llegadas: int = 0
    porcentaje_mesas_completas: float = 0.0
    invitados_con_novedades: int = 0
    primera_llegada: str = "Sin llegadas"
    ultima_llegada: str = "Sin llegadas"
    intervalos_llegadas: tuple[IntervaloLlegadas, ...] = ()
    inicio_evento_valido: bool = False

    @property
    def porcentaje_invitados(self) -> float:
        return self.porcentaje_llegadas

    @property
    def porcentaje_mesas(self) -> float:
        return self.porcentaje_mesas_completas

    @property
    def invitados_con_novedad(self) -> int:
        return self.invitados_con_novedades


@dataclass(frozen=True)
class ResultadoDashboard:
    ok: bool
    estado: str
    mensaje: str
    indicadores: IndicadoresDashboard = IndicadoresDashboard()


class DashboardRefreshController:
    def __init__(self) -> None:
        self.generation = 0
        self.task: Any = None

    def is_current(self, generation: int) -> bool:
        return generation == self.generation

    def start(self, page: Any, runner: Any) -> bool:
        if self.task is not None and not self.task.done():
            return False
        self.generation += 1
        self.task = page.run_task(runner, self.generation)
        return True

    def stop(self) -> None:
        self.generation += 1
        if self.task is not None and not self.task.done():
            self.task.cancel()
        self.task = None

    def finish(self, generation: int) -> None:
        if self.is_current(generation):
            self.task = None


def _datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _hora(value: datetime, zona: Any = None) -> str:
    local = value.astimezone(zona) if zona is not None else value
    hour = local.hour % 12 or 12
    suffix = "a. m." if local.hour < 12 else "p. m."
    return f"{hour}:{local.minute:02d} {suffix}"


def _etiqueta_intervalo(inicio: datetime, final: datetime) -> str:
    return f"{_hora(inicio)}–{_hora(final)}"


def construir_intervalos_llegadas(
    inicio_evento: Any,
    llegadas: list[datetime],
) -> tuple[IntervaloLlegadas, ...]:
    inicio = _datetime(inicio_evento)
    if inicio is None:
        return ()
    cantidades = [0] * 8
    limite = inicio + timedelta(hours=2)
    for llegada in llegadas:
        value = llegada if llegada.tzinfo is not None else llegada.replace(tzinfo=timezone.utc)
        value = value.astimezone(inicio.tzinfo)
        if value < inicio or value >= limite:
            continue
        index = int((value - inicio).total_seconds() // 900)
        if 0 <= index < 8:
            cantidades[index] += 1
    return tuple(
        IntervaloLlegadas(
            inicio=inicio + timedelta(minutes=15 * index),
            final=inicio + timedelta(minutes=15 * (index + 1)) - timedelta(seconds=1),
            etiqueta=_etiqueta_intervalo(
                inicio + timedelta(minutes=15 * index),
                inicio + timedelta(minutes=15 * (index + 1)) - timedelta(seconds=1),
            ),
            cantidad=cantidades[index],
        )
        for index in range(8)
    )


def calcular_indicadores_dashboard(
    invitados: list[dict[str, Any]],
    mesas: list[dict[str, Any]],
    inicio_evento: Any = None,
) -> IndicadoresDashboard:
    activos_por_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(invitados):
        if str(safe_get(row, "ivt_estado", "Activo")) != "Activo":
            continue
        stable_id = str(safe_get(row, "ivt_invitado_uuid") or safe_get(row, "ivt_invitado_id") or f"row:{index}")
        previous = activos_por_id.get(stable_id)
        if previous is None:
            activos_por_id[stable_id] = row
        else:
            activos_por_id[stable_id] = {
                **previous,
                "ivt_tiene_novedad": bool(safe_get(previous, "ivt_tiene_novedad", False))
                or bool(safe_get(row, "ivt_tiene_novedad", False)),
            }
    activos = list(activos_por_id.values())
    total_invitados = len(activos)
    invitados_llegaron = sum(bool(safe_get(row, "ivt_llegada_confirmada", False)) for row in activos)
    invitados_pendientes = total_invitados - invitados_llegaron
    invitados_con_novedades = sum(bool(safe_get(row, "ivt_tiene_novedad", False)) for row in activos)

    timestamps = sorted(
        value
        for row in activos
        if bool(safe_get(row, "ivt_llegada_confirmada", False))
        and (value := _datetime(safe_get(row, "ivt_fecha_hora_conf_llegada"))) is not None
    )
    inicio = _datetime(inicio_evento)
    zona = inicio.tzinfo if inicio is not None else (timestamps[0].tzinfo if timestamps else None)

    mesas_activas = {
        int(value) for row in mesas
        if str(safe_get(row, "mes_estado", "Activo")) == "Activo"
        and (value := safe_get(row, "mes_mesa_id")) is not None
    }
    llegadas_por_mesa: dict[int, list[bool]] = {}
    for row in activos:
        try:
            mesa_id = int(safe_get(row, "ivt_mesa_id"))
        except (TypeError, ValueError):
            continue
        if mesa_id in mesas_activas:
            llegadas_por_mesa.setdefault(mesa_id, []).append(bool(safe_get(row, "ivt_llegada_confirmada", False)))
    mesas_con_invitados = len(llegadas_por_mesa)
    mesas_completas = sum(all(values) for values in llegadas_por_mesa.values())
    mesas_pendientes = len(mesas_activas) - mesas_completas
    mesas_parciales = sum(len(values) >= 2 and any(values) and not all(values) for values in llegadas_por_mesa.values())
    mesas_sin_llegadas = sum(not any(values) for values in llegadas_por_mesa.values())

    return IndicadoresDashboard(
        total_invitados=total_invitados,
        invitados_llegaron=invitados_llegaron,
        invitados_pendientes=invitados_pendientes,
        porcentaje_llegadas=(invitados_llegaron / total_invitados * 100) if total_invitados else 0.0,
        porcentaje_pendientes=(invitados_pendientes / total_invitados * 100) if total_invitados else 0.0,
        total_mesas=len(mesas_activas),
        mesas_con_invitados=mesas_con_invitados,
        mesas_completas=mesas_completas,
        mesas_pendientes=mesas_pendientes,
        mesas_parciales=mesas_parciales,
        mesas_sin_llegadas=mesas_sin_llegadas,
        porcentaje_mesas_completas=(mesas_completas / len(mesas_activas) * 100) if mesas_activas else 0.0,
        invitados_con_novedades=invitados_con_novedades,
        primera_llegada=_hora(timestamps[0], zona) if timestamps else "Sin llegadas",
        ultima_llegada=_hora(timestamps[-1], zona) if timestamps else "Sin llegadas",
        intervalos_llegadas=construir_intervalos_llegadas(inicio_evento, timestamps),
        inicio_evento_valido=inicio is not None,
    )


def obtener_indicadores_dashboard(contexto: dict[str, Any] | None, supabase: Any) -> ResultadoDashboard:
    evento = (contexto or {}).get("evento_actual") or {}
    key = evento_key(evento)
    if key is None:
        return ResultadoDashboard(False, "event_required", "Selecciona un evento activo.")
    if not puede_consultar(contexto):
        return ResultadoDashboard(False, "forbidden", "No tienes acceso de consulta a este evento.")
    if supabase is None:
        return ResultadoDashboard(False, "connection_error", "No existe una conexión de datos disponible.")
    try:
        invitados_response = (
            supabase.table("evp_ivt_invitado")
            .select("ivt_invitado_uuid,ivt_mesa_id,ivt_llegada_confirmada,ivt_fecha_hora_conf_llegada,ivt_tiene_novedad,ivt_estado")
            .eq("ivt_cuenta_id", key[0]).eq("ivt_evento_id", key[1]).eq("ivt_estado", "Activo").execute()
        )
        mesas_response = (
            supabase.table("evp_mes_mesa").select("mes_mesa_id,mes_estado")
            .eq("mes_cuenta_id", key[0]).eq("mes_evento_id", key[1]).eq("mes_estado", "Activo").execute()
        )
        invitados = [row for item in extract_data(invitados_response) if (row := to_dict(item))]
        mesas = [row for item in extract_data(mesas_response) if (row := to_dict(item))]
        return ResultadoDashboard(
            True, "ready", "Indicadores actualizados.",
            calcular_indicadores_dashboard(invitados, mesas, evento.get("fecha_hora_inicio")),
        )
    except Exception as ex:
        print("[DASHBOARD][ERROR]", type(ex).__name__, str(ex))
        return ResultadoDashboard(False, "error", "No fue posible cargar los indicadores del evento.")
