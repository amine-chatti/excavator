from __future__ import annotations

from typing import Protocol

from excavator.core.symbols import ExtractionResult


class LanguageAnalyzer(Protocol):
    language: str

    def file_extensions(self) -> tuple[str, ...]: ...

    def extract_symbols(self, source: bytes, path: str) -> ExtractionResult: ...
