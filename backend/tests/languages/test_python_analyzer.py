from __future__ import annotations

import hashlib
import io
import sysconfig
import tokenize
from pathlib import Path

import pytest

from excavator.core.symbols import ExtractedSymbol, ParseStatus, SymbolKind
from excavator.languages.python import PythonAnalyzer
from excavator.languages.python.analyzer import MAX_SOURCE_BYTES

ANALYZER = PythonAnalyzer()


def _extract(source: str) -> list[ExtractedSymbol]:
    result = ANALYZER.extract_symbols(source.encode(), "sample.py")
    assert result.status is ParseStatus.OK
    return list(result.symbols)


def _assert_invariants(source: str, symbols: list[ExtractedSymbol]) -> None:
    line_count = len(source.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    keys = {(symbol.qualified_name, symbol.occurrence_index) for symbol in symbols}
    assert len(keys) == len(symbols)
    for symbol in symbols:
        assert 1 <= symbol.start_line <= symbol.def_line <= symbol.end_line <= line_count
        if symbol.parent_qualified_name is not None:
            parent = next(
                item for item in symbols if item.qualified_name == symbol.parent_qualified_name
            )
            assert parent.start_line <= symbol.start_line
            assert symbol.end_line <= parent.end_line


def test_extracts_functions_classes_methods_and_nested_definitions() -> None:
    symbols = _extract(
        "def top():\n"
        "    def inner():\n"
        "        pass\n"
        "    return inner\n"
        "class A:\n"
        "    async def method(self):\n"
        "        pass\n"
        "    class B:\n"
        "        def method(self):\n"
        "            pass\n"
    )

    assert [(symbol.kind, symbol.qualified_name) for symbol in symbols] == [
        (SymbolKind.FUNCTION, "top"),
        (SymbolKind.FUNCTION, "top.<locals>.inner"),
        (SymbolKind.CLASS, "A"),
        (SymbolKind.METHOD, "A.method"),
        (SymbolKind.CLASS, "A.B"),
        (SymbolKind.METHOD, "A.B.method"),
    ]
    _assert_invariants(
        "def top():\n"
        "    def inner():\n"
        "        pass\n"
        "    return inner\n"
        "class A:\n"
        "    async def method(self):\n"
        "        pass\n"
        "    class B:\n"
        "        def method(self):\n"
        "            pass\n",
        symbols,
    )


def test_decorators_start_at_first_decorator_and_hash_includes_decorators() -> None:
    symbols = _extract(
        "@first\n@second(\n    1,\n)\ndef f():\n    pass\n@decorator\nclass C:\n    pass\n"
    )

    assert [(item.start_line, item.def_line, item.end_line) for item in symbols] == [
        (1, 5, 6),
        (7, 8, 9),
    ]


def test_one_line_and_trailing_comments_have_precise_ranges() -> None:
    symbols = _extract("def one(): pass\n\ndef two():\n    pass\n# comment\n\n")

    assert [(item.qualified_name, item.start_line, item.end_line) for item in symbols] == [
        ("one", 1, 1),
        ("two", 3, 4),
    ]


def test_duplicate_qualified_names_are_numbered_in_source_order() -> None:
    symbols = _extract(
        "class A:\n"
        "    @property\n"
        "    def x(self): pass\n"
        "    @x.setter\n"
        "    def x(self, value): pass\n"
        "from typing import overload\n"
        "@overload\n"
        "def f(x: int): ...\n"
        "@overload\n"
        "def f(x: str): ...\n"
        "if True:\n"
        "    def conditional(): pass\n"
        "else:\n"
        "    def conditional(): pass\n"
    )

    assert [(item.qualified_name, item.occurrence_index) for item in symbols] == [
        ("A", 0),
        ("A.x", 0),
        ("A.x", 1),
        ("f", 0),
        ("f", 1),
        ("conditional", 0),
        ("conditional", 1),
    ]


def test_ignores_lambdas_variables_and_attributes_and_finds_control_flow_defs() -> None:
    symbols = _extract(
        "value = lambda: None\n"
        "class A:\n"
        "    attribute = 1\n"
        "if True:\n"
        "    def in_if(): pass\n"
        "try:\n"
        "    def in_try(): pass\n"
        "except Exception:\n"
        "    def in_except(): pass\n"
        "with open('x'):\n"
        "    def in_with(): pass\n"
    )

    assert [item.qualified_name for item in symbols] == [
        "A",
        "in_if",
        "in_try",
        "in_except",
        "in_with",
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", []),
        ("# comment\n# another\n", []),
        ("def f():\r\n    pass\r\n", [("f", 1, 2)]),
        ("def f():\r    pass\r", [("f", 1, 2)]),
        ("def f():\n\tpass\n", [("f", 1, 2)]),
        ("def f():\n\x0c    pass\n", [("f", 1, 2)]),
    ],
)
def test_empty_comments_and_line_endings(source: str, expected: list[tuple[str, int, int]]) -> None:
    assert [
        (item.qualified_name, item.start_line, item.end_line) for item in _extract(source)
    ] == expected


def test_encoding_detection_supports_bom_and_cookie() -> None:
    bom = b"\xef\xbb\xbfdef f():\n    pass\n"
    latin1 = b"# -*- coding: latin-1 -*-\ndef caf\xe9():\n    pass\n"

    assert ANALYZER.extract_symbols(bom, "bom.py").symbols[0].name == "f"
    assert ANALYZER.extract_symbols(latin1, "latin.py").symbols[0].name == "café"


@pytest.mark.parametrize(
    "source",
    [
        b'print "old"\n',
        b"(unclosed\n",
        b"x = \x00\n",
        b"# coding: utf-8\nname = '\xff'\n",
        b"x" * (MAX_SOURCE_BYTES + 1),
    ],
)
def test_invalid_sources_return_truncated_syntax_errors(source: bytes) -> None:
    result = ANALYZER.extract_symbols(source, "bad.py")

    assert result.status is ParseStatus.SYNTAX_ERROR
    assert result.symbols == ()
    assert result.error is not None
    assert len(result.error) <= 200


def test_deep_input_does_not_escape_or_hang() -> None:
    result = ANALYZER.extract_symbols(("(" * 1100 + "1" + ")" * 1100).encode(), "deep.py")
    assert result.status is ParseStatus.SYNTAX_ERROR


def test_body_hash_is_whitespace_sensitive_but_line_ending_insensitive() -> None:
    lf = "def f():\n    return 1\n"
    crlf = lf.replace("\n", "\r\n")
    changed = "def f():\n    return  1\n"

    first = ANALYZER.extract_symbols(lf.encode(), "f.py").symbols[0].body_hash
    second = ANALYZER.extract_symbols(crlf.encode(), "f.py").symbols[0].body_hash
    third = ANALYZER.extract_symbols(changed.encode(), "f.py").symbols[0].body_hash
    assert first == second == hashlib.sha256(lf.rstrip("\n").encode()).hexdigest()
    assert third != first


def test_dogfoods_backend_and_stdlib_sample() -> None:
    paths = sorted(Path(__file__).resolve().parents[2].rglob("src/**/*.py"))
    for path in paths:
        source = path.read_bytes()
        result = ANALYZER.extract_symbols(source, str(path))
        if result.status is ParseStatus.OK:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
            _assert_invariants(source.decode(encoding), list(result.symbols))

    stdlib = Path(sysconfig.get_paths()["stdlib"])
    if stdlib.is_dir():
        for path in sorted(stdlib.rglob("*.py"))[:300]:
            source = path.read_bytes()
            result = ANALYZER.extract_symbols(source, str(path))
            if result.status is ParseStatus.OK:
                encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
                _assert_invariants(source.decode(encoding), list(result.symbols))
