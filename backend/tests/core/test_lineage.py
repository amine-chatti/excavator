from __future__ import annotations

from dataclasses import dataclass

from excavator.core.language import LanguageAnalyzer
from excavator.core.lineage import (
    FileHistory,
    FileVersion,
    SymbolLineage,
    build_file_history,
)
from excavator.core.matching import ChangeKind
from excavator.core.symbols import ExtractedSymbol, ExtractionResult, ParseStatus, SymbolKind


def symbol(
    name: str,
    *,
    qualified_name: str | None = None,
    parent: str | None = None,
    line: int = 1,
    occurrence: int = 0,
    body_hash: str = "same",
    kind: SymbolKind = SymbolKind.FUNCTION,
) -> ExtractedSymbol:
    return ExtractedSymbol(
        kind,
        name,
        qualified_name or name,
        parent,
        line,
        line,
        line,
        occurrence,
        body_hash,
    )


@dataclass
class FakeAnalyzer:
    results: dict[bytes, ExtractionResult]

    language: str = "fake"

    def file_extensions(self) -> tuple[str, ...]:
        return (".fake",)

    def extract_symbols(self, source: bytes, path: str) -> ExtractionResult:
        del path
        return self.results[source]


def result(*symbols: ExtractedSymbol) -> ExtractionResult:
    return ExtractionResult(ParseStatus.OK, tuple(symbols))


def history(*versions: FileVersion, results: dict[bytes, ExtractionResult]) -> FileHistory:
    return build_file_history(versions, FakeAnalyzer(results))


def event_kinds(lineage: SymbolLineage) -> list[ChangeKind]:
    return [event.change for event in lineage.events]


def test_empty_history() -> None:
    assert history(results={}).lineages == ()


def test_single_version_adds_every_symbol() -> None:
    first = symbol("first", line=2)
    second = symbol("second", line=1)

    built = history(
        FileVersion("one", "file.fake", b"one"),
        results={b"one": result(first, second)},
    )

    assert [lineage.events[0].symbol for lineage in built.lineages] == [second, first]
    assert all(event_kinds(lineage) == [ChangeKind.ADDED] for lineage in built.lineages)


def test_identical_versions_do_not_add_events() -> None:
    current = symbol("f")

    built = history(
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", b"two"),
        results={b"one": result(current), b"two": result(current)},
    )

    assert len(built.lineages) == 1
    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED]


def test_modified_symbol_accumulates_events() -> None:
    versions = (
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", b"two"),
        FileVersion("three", "file.fake", b"three"),
    )
    built = history(
        *versions,
        results={
            b"one": result(symbol("f", body_hash="one")),
            b"two": result(symbol("f", body_hash="two")),
            b"three": result(symbol("f", body_hash="three")),
        },
    )

    assert event_kinds(built.lineages[0]) == [
        ChangeKind.ADDED,
        ChangeKind.MODIFIED,
        ChangeKind.MODIFIED,
    ]
    assert [event.commit_sha for event in built.lineages[0].events] == ["one", "two", "three"]


def test_rename_then_modify_keeps_one_lineage() -> None:
    built = history(
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", b"two"),
        FileVersion("three", "file.fake", b"three"),
        results={
            b"one": result(symbol("old", body_hash="same")),
            b"two": result(symbol("new", body_hash="same")),
            b"three": result(symbol("new", body_hash="changed")),
        },
    )

    assert event_kinds(built.lineages[0]) == [
        ChangeKind.ADDED,
        ChangeKind.RENAMED,
        ChangeKind.MODIFIED,
    ]


def test_moved_method_keeps_one_lineage() -> None:
    old = symbol("m", qualified_name="A.m", parent="A", kind=SymbolKind.METHOD)
    new = symbol("m", qualified_name="B.m", parent="B", kind=SymbolKind.METHOD)

    built = history(
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", b"two"),
        results={b"one": result(old), b"two": result(new)},
    )

    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED, ChangeKind.MOVED]
    assert built.lineages[0].events[-1].symbol == new


def test_removed_then_readded_starts_new_lineage() -> None:
    current = symbol("f")

    built = history(
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", None),
        FileVersion("three", "file.fake", b"three"),
        results={b"one": result(current), b"three": result(current)},
    )

    assert len(built.lineages) == 2
    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED, ChangeKind.REMOVED]
    assert event_kinds(built.lineages[1]) == [ChangeKind.ADDED]


def test_syntax_error_keeps_baseline_and_records_commit() -> None:
    before = symbol("f", body_hash="before")
    after = symbol("f", body_hash="after")

    built = history(
        FileVersion("one", "file.fake", b"one"),
        FileVersion("broken", "file.fake", b"broken"),
        FileVersion("three", "file.fake", b"three"),
        results={
            b"one": result(before),
            b"broken": ExtractionResult(ParseStatus.SYNTAX_ERROR, error="bad"),
            b"three": result(after),
        },
    )

    assert built.skipped_commits == ("broken",)
    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED, ChangeKind.MODIFIED]


def test_first_syntax_error_leaves_empty_baseline() -> None:
    current = symbol("f")

    built = history(
        FileVersion("broken", "file.fake", b"broken"),
        FileVersion("valid", "file.fake", b"valid"),
        results={
            b"broken": ExtractionResult(ParseStatus.SYNTAX_ERROR),
            b"valid": result(current),
        },
    )

    assert built.skipped_commits == ("broken",)
    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED]


def test_duplicate_qualified_names_have_separate_lineages() -> None:
    first = symbol("x", qualified_name="A.x", parent="A", occurrence=0, line=1)
    second = symbol("x", qualified_name="A.x", parent="A", occurrence=1, line=2)

    built = history(
        FileVersion("one", "file.fake", b"one"),
        results={b"one": result(first, second)},
    )

    assert len(built.lineages) == 2
    assert [lineage.events[0].symbol for lineage in built.lineages] == [first, second]


def test_repeated_builds_are_equal_and_invariants_hold() -> None:
    current = symbol("f")
    versions = (
        FileVersion("one", "file.fake", b"one"),
        FileVersion("two", "file.fake", None),
        FileVersion("three", "file.fake", b"three"),
    )
    results = {b"one": result(current), b"three": result(current)}

    first = build_file_history(versions, FakeAnalyzer(results))
    second = build_file_history(versions, FakeAnalyzer(results))

    assert first == second
    for lineage in first.lineages:
        assert lineage.events[0].change is ChangeKind.ADDED
        removed = False
        for event in lineage.events:
            assert not removed
            if event.change is ChangeKind.REMOVED:
                removed = True


def test_real_python_analyzer_end_to_end() -> None:
    from excavator.languages.python import PythonAnalyzer

    analyzer: LanguageAnalyzer = PythonAnalyzer()
    versions = (
        FileVersion("one", "file.py", b"def f():\n    return 1\n"),
        FileVersion("two", "file.py", b"def f():\n    return 2\n"),
    )

    built = build_file_history(versions, analyzer)

    assert event_kinds(built.lineages[0]) == [ChangeKind.ADDED, ChangeKind.MODIFIED]
