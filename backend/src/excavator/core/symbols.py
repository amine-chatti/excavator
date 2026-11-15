from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SymbolKind(StrEnum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"


class ParseStatus(StrEnum):
    OK = "ok"
    SYNTAX_ERROR = "syntax_error"


@dataclass(frozen=True, slots=True)
class ExtractedSymbol:
    kind: SymbolKind
    name: str
    qualified_name: str
    parent_qualified_name: str | None
    start_line: int
    def_line: int
    end_line: int
    occurrence_index: int
    body_hash: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    status: ParseStatus
    symbols: tuple[ExtractedSymbol, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status is not ParseStatus.OK and self.symbols:
            object.__setattr__(self, "symbols", ())
        if self.error is not None:
            object.__setattr__(self, "error", self.error[:200])
