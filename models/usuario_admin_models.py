from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    telefono: str | None
    cuentas: tuple[UsuarioCuentaResumen, ...]
    eventos: tuple[UsuarioEventoResumen, ...]
    acceso_efectivo: AccesoEfectivoUsuario
    advertencias: tuple[str, ...] = ()
    creado: datetime | str | None = None
    modificado: datetime | str | None = None


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
