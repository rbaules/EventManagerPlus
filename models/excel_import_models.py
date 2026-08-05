from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportRowRaw:
    excel_row: int
    values: dict[str, Any]


@dataclass(frozen=True)
class ImportRowNormalized:
    excel_row: int
    invitation_code: str
    recipient: str
    guest_order: int | None
    guest_name: str
    guest_name_normalized: str
    phone: str | None
    email: str | None
    is_primary: bool | None
    table_code: str | None
    table_name: str | None
    table_name_normalized: str | None


@dataclass(frozen=True)
class ImportValidationIssue:
    excel_row: int
    column: str
    original_value: str
    code: str
    message: str
    severity: str


@dataclass(frozen=True)
class ImportValidationError(ImportValidationIssue):
    severity: str = "ERROR"


@dataclass(frozen=True)
class ImportValidationWarning(ImportValidationIssue):
    severity: str = "ADVERTENCIA"


@dataclass(frozen=True)
class InvitationImportGroup:
    code: str
    recipient: str
    rows: tuple[ImportRowNormalized, ...]
    reserved_seats: int


@dataclass(frozen=True)
class TableImportGroup:
    code: str
    name: str
    rows: tuple[int, ...]


@dataclass(frozen=True)
class ImportSummary:
    processed_rows: int = 0
    invitations: int = 0
    guests: int = 0
    tables: int = 0
    errors: int = 0
    warnings: int = 0


@dataclass(frozen=True)
class ImportPreview:
    filename: str
    raw_rows: tuple[ImportRowRaw, ...] = ()
    rows: tuple[ImportRowNormalized, ...] = ()
    invitations: tuple[InvitationImportGroup, ...] = ()
    tables: tuple[TableImportGroup, ...] = ()
    errors: tuple[ImportValidationError, ...] = ()
    warnings: tuple[ImportValidationWarning, ...] = ()
    summary: ImportSummary = field(default_factory=ImportSummary)

    @property
    def is_valid(self) -> bool:
        return not self.errors and bool(self.rows)
