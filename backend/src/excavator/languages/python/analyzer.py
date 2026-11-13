from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize
from collections.abc import Iterable

from excavator.core.symbols import (
    ExtractedSymbol,
    ExtractionResult,
    ParseStatus,
    SymbolKind,
)

MAX_SOURCE_BYTES = 2_000_000
_LINE_SPLITTER = re.compile(r"\r\n|\r|\n")
_DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class PythonAnalyzer:
    language = "python"

    def file_extensions(self) -> tuple[str, ...]:
        return (".py",)

    def extract_symbols(self, source: bytes, path: str) -> ExtractionResult:
        del path
        if len(source) > MAX_SOURCE_BYTES:
            return ExtractionResult(ParseStatus.SYNTAX_ERROR, error="source too large")

        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
            text = source.decode(encoding)
        except (SyntaxError, UnicodeDecodeError, LookupError) as exc:
            return ExtractionResult(
                ParseStatus.SYNTAX_ERROR,
                error=f"unable to decode source: {exc}",
            )

        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            return ExtractionResult(ParseStatus.SYNTAX_ERROR, error=str(exc))

        lines = _split_lines(text)
        symbols: list[ExtractedSymbol] = []
        occurrences: dict[str, int] = {}
        self._visit_block(tree.body, None, "module", lines, symbols, occurrences)
        return ExtractionResult(ParseStatus.OK, symbols=tuple(symbols))

    def _visit_block(
        self,
        statements: Iterable[ast.stmt],
        scope_name: str | None,
        scope_kind: str,
        lines: list[str],
        symbols: list[ExtractedSymbol],
        occurrences: dict[str, int],
    ) -> None:
        for statement in statements:
            self._visit_statement(
                statement, scope_name, scope_kind, lines, symbols, occurrences
            )

    def _visit_statement(
        self,
        statement: ast.stmt,
        scope_name: str | None,
        scope_kind: str,
        lines: list[str],
        symbols: list[ExtractedSymbol],
        occurrences: dict[str, int],
    ) -> None:
        if isinstance(statement, _DEFINITION_NODES):
            is_class = isinstance(statement, ast.ClassDef)
            kind = SymbolKind.CLASS if is_class else (
                SymbolKind.METHOD if scope_kind == "class" else SymbolKind.FUNCTION
            )
            qualified_name = _qualified_name(statement.name, scope_name, scope_kind)
            index = occurrences.get(qualified_name, 0)
            occurrences[qualified_name] = index + 1
            start_line = (
                statement.decorator_list[0].lineno
                if statement.decorator_list
                else statement.lineno
            )
            symbols.append(
                ExtractedSymbol(
                    kind=kind,
                    name=statement.name,
                    qualified_name=qualified_name,
                    parent_qualified_name=scope_name,
                    start_line=start_line,
                    def_line=statement.lineno,
                    end_line=statement.end_lineno or statement.lineno,
                    occurrence_index=index,
                    body_hash=_body_hash(
                        lines, start_line, statement.end_lineno or statement.lineno
                    ),
                )
            )
            self._visit_block(
                statement.body,
                qualified_name,
                "class" if is_class else "function",
                lines,
                symbols,
                occurrences,
            )
            return

        for child in ast.iter_child_nodes(statement):
            if isinstance(child, ast.stmt):
                self._visit_statement(
                    child, scope_name, scope_kind, lines, symbols, occurrences
                )
            elif isinstance(child, ast.ExceptHandler) or isinstance(child, ast.match_case):
                self._visit_block(
                    child.body, scope_name, scope_kind, lines, symbols, occurrences
                )


def _qualified_name(name: str, scope_name: str | None, scope_kind: str) -> str:
    if scope_name is None:
        return name
    if scope_kind == "function":
        return f"{scope_name}.<locals>.{name}"
    return f"{scope_name}.{name}"


def _split_lines(text: str) -> list[str]:
    return _LINE_SPLITTER.split(text)


def _body_hash(
    lines: list[str], start_line: int, end_line: int
) -> str:
    body = "\n".join(lines[start_line - 1 : end_line])
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
