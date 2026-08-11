from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID


ESTADOS_USUARIO_8C = frozenset({"Preregistrado", "Activo", "Inactivo"})


def _nombre(value: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized or len(normalized) > 50:
        raise ValueError("INVALID_USER_NAME")
    return normalized


def _email(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("INVALID_EMAIL")
    return normalized


def _uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("USER_NOT_FOUND") from exc


@dataclass(frozen=True)
class CrearUsuarioRequest:
    nombre: str
    email: str
    rol: str
    cuenta_id: int
    evento_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "nombre", _nombre(self.nombre))
        object.__setattr__(self, "email", _email(self.email))
        rol = str(self.rol or "").strip()
        if rol not in {"Master", "Administrador", "Operador", "Consulta"}:
            raise ValueError("INVALID_ACCOUNT_ROLE")
        object.__setattr__(self, "rol", rol)
        for field_name in ("cuenta_id", "evento_id"):
            try:
                normalized = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError("ACTIVE_CONTEXT_REQUIRED") from exc
            if normalized <= 0:
                raise ValueError("ACTIVE_CONTEXT_REQUIRED")
            object.__setattr__(self, field_name, normalized)


@dataclass(frozen=True)
class ActualizarPreferenciasRequest:
    cuenta_id: int
    evento_id: int

    def __post_init__(self) -> None:
        for field_name in ("cuenta_id", "evento_id"):
            try:
                value = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError("INVALID_PREFERENCES") from exc
            if value <= 0:
                raise ValueError("INVALID_PREFERENCES")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class CambiarRolCuentaRequest:
    usuario_id: str
    cuenta_id: int
    rol: str
    evento_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        if self.rol not in {"Administrador", "Operador", "Consulta"}:
            raise ValueError("ROLE_CHANGE_FORBIDDEN")
        if int(self.cuenta_id) <= 0:
            raise ValueError("INVALID_ACCOUNT")
        object.__setattr__(self, "cuenta_id", int(self.cuenta_id))
        if self.evento_id not in (None, ""):
            if int(self.evento_id) <= 0:
                raise ValueError("INVALID_EVENT")
            object.__setattr__(self, "evento_id", int(self.evento_id))


@dataclass(frozen=True)
class PromoverMasterRequest:
    usuario_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))


@dataclass(frozen=True)
class RetirarMasterRequest:
    usuario_id: str
    cuenta_id: int
    rol: str
    evento_id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        if self.rol not in {"Administrador", "Operador", "Consulta"}:
            raise ValueError("INVALID_ACCOUNT_ROLE")
        if int(self.cuenta_id) <= 0:
            raise ValueError("ACCOUNT_REQUIRED")
        object.__setattr__(self, "cuenta_id", int(self.cuenta_id))
        if self.evento_id in (None, ""):
            raise ValueError("EVENT_REQUIRED")
        if self.evento_id not in (None, ""):
            if int(self.evento_id) <= 0:
                raise ValueError("INVALID_EVENT")
            object.__setattr__(self, "evento_id", int(self.evento_id))


@dataclass(frozen=True)
class CambiarEstadoCuentaRequest:
    usuario_id: str
    cuenta_id: int
    estado: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        if self.estado not in {"Activo", "Inactivo"}:
            raise ValueError("INVALID_STATUS")
        if int(self.cuenta_id) <= 0:
            raise ValueError("INVALID_ACCOUNT")
        object.__setattr__(self, "cuenta_id", int(self.cuenta_id))


@dataclass(frozen=True)
class ActualizarUsuarioRequest:
    usuario_id: str
    nombre: str
    email: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        object.__setattr__(self, "nombre", _nombre(self.nombre))
        object.__setattr__(self, "email", _email(self.email))


@dataclass(frozen=True)
class CambiarEstadoUsuarioRequest:
    usuario_id: str
    estado: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        if self.estado not in ESTADOS_USUARIO_8C:
            raise ValueError("INVALID_STATUS")


@dataclass(frozen=True)
class CambiarMasterRequest:
    usuario_id: str
    es_master: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "usuario_id", _uuid(self.usuario_id))
        if type(self.es_master) is not bool:
            raise ValueError("USER_ADMIN_FORBIDDEN")


@dataclass(frozen=True)
class ResultadoUsuarioOperacion:
    ok: bool
    codigo: str
    mensaje: str
    usuario_id: str | None = None
    datos: dict | None = None


@dataclass(frozen=True)
class UsuarioCuentaResumen:
    cuenta_id: int
    cuenta_nombre: str
    rol: str
    estado_relacion: str
    estado_cuenta: str
    es_predeterminada: bool = False
    acceso_heredado: bool = False
    acceso_efectivo: bool = False


@dataclass(frozen=True)
class UsuarioEventoResumen:
    cuenta_id: int
    cuenta_nombre: str
    evento_id: int
    evento_nombre: str
    estado_evento: str
    fase_evento: str
    estado_relacion: str | None
    es_predeterminado: bool = False
    tipo_acceso: str = "Sin acceso"
    acceso_efectivo: bool = False


@dataclass(frozen=True)
class AccesoEfectivoUsuario:
    es_master: bool
    cuentas_accesibles: tuple[int, ...] = ()
    eventos_accesibles: tuple[tuple[int, int], ...] = ()
    razones_acceso: tuple[str, ...] = ()
    advertencias: tuple[str, ...] = ()


@dataclass(frozen=True)
class UsuarioResumen:
    usuario_id: str
    nombre: str
    email: str
    estado: str
    es_master: bool
    auth_uuid_presente: bool
    cuentas_visibles: tuple[str, ...] = ()
    roles_visibles: tuple[str, ...] = ()
    cantidad_eventos_asignados: int = 0
    cantidad_cuentas_accesibles: int = 0
    cantidad_eventos_accesibles: int = 0
    tiene_advertencia_auth: bool = False
    acceso_global: bool = False


@dataclass(frozen=True)
class UsuarioDetalle:
    usuario_id: str
    nombre: str
    nombre_abreviado: str
    email: str
    estado: str
    es_master: bool
    auth_uuid_presente: bool
    cuenta_id_default: int | None
    evento_id_default: int | None
    cuenta_default_nombre: str | None
    evento_default_nombre: str | None
    telefono: str | None
    cuentas: tuple[UsuarioCuentaResumen, ...]
    eventos: tuple[UsuarioEventoResumen, ...]
    acceso_efectivo: AccesoEfectivoUsuario
    advertencias: tuple[str, ...] = ()
    creado: datetime | str | None = None
    modificado: datetime | str | None = None
    creado_por_actor: bool = False


@dataclass(frozen=True)
class ResultadoPaginadoUsuarios:
    items: tuple[UsuarioResumen, ...] = ()
    pagina: int = 1
    tamano_pagina: int = 20
    total: int = 0
    total_paginas: int = 0
    has_previous: bool = False
    has_next: bool = False
    estado: str = "ready"
    mensaje: str = ""
    cuentas_filtro: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ResultadoDetalleUsuario:
    ok: bool
    estado: str
    mensaje: str
    detalle: UsuarioDetalle | None = None
