from __future__ import annotations

from dataclasses import fields, is_dataclass

from excavator.core.symbols import (
    ExtractedSymbol,
    ExtractionResult,
    ParseStatus,
    SymbolKind,
)


def test_core_types_are_frozen_slot_dataclasses() -> None:
    assert is_dataclass(ExtractedSymbol)
    assert is_dataclass(ExtractionResult)
    assert "__dict__" not in ExtractedSymbol.__slots__
    assert [field.name for field in fields(ExtractedSymbol)] == [
        "kind",
        "name",
        "qualified_name",
        "parent_qualified_name",
        "start_line",
        "def_line",
        "end_line",
        "occurrence_index",
        "body_hash",
    ]


def test_extraction_result_truncates_errors_and_discards_failed_symbols() -> None:
    symbol = ExtractedSymbol(SymbolKind.FUNCTION, "f", "f", None, 1, 1, 1, 0, "a" * 64)
    result = ExtractionResult(ParseStatus.SYNTAX_ERROR, (symbol,), "x" * 201)

    assert result.symbols == ()
    assert result.error == "x" * 200
