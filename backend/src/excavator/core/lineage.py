"""Build per-symbol lineages across ordered versions of one file."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from excavator.core.language import LanguageAnalyzer
from excavator.core.matching import ChangeKind, match_symbols
from excavator.core.symbols import ExtractedSymbol, ParseStatus


@dataclass(frozen=True, slots=True)
class FileVersion:
    commit_sha: str
    path: str
    source: bytes | None


@dataclass(frozen=True, slots=True)
class LineageEvent:
    commit_sha: str
    change: ChangeKind
    symbol: ExtractedSymbol | None


@dataclass(frozen=True, slots=True)
class SymbolLineage:
    events: tuple[LineageEvent, ...]


@dataclass(frozen=True, slots=True)
class FileHistory:
    lineages: tuple[SymbolLineage, ...]
    skipped_commits: tuple[str, ...]


def build_file_history(versions: Sequence[FileVersion], analyzer: LanguageAnalyzer) -> FileHistory:
    """Build chronological symbol lineages without filesystem or VCS access."""
    baseline: tuple[ExtractedSymbol, ...] = ()
    owners: dict[int, int] = {}
    lineages: list[list[LineageEvent]] = []
    starts: list[tuple[int, int, int]] = []
    skipped: list[str] = []

    for version_index, version in enumerate(versions):
        if version.source is None:
            current: tuple[ExtractedSymbol, ...] = ()
        else:
            result = analyzer.extract_symbols(version.source, version.path)
            if result.status is ParseStatus.SYNTAX_ERROR:
                skipped.append(version.commit_sha)
                continue
            current = result.symbols

        changes = match_symbols(baseline, current)
        current_owners: dict[int, int] = {}
        for change in changes:
            if change.kind is ChangeKind.UNCHANGED:
                assert change.old is not None
                assert change.new is not None
                current_owners[id(change.new)] = owners[id(change.old)]
            elif change.kind is ChangeKind.ADDED:
                assert change.new is not None
                lineage_index = len(lineages)
                lineages.append(
                    [
                        LineageEvent(
                            version.commit_sha,
                            ChangeKind.ADDED,
                            change.new,
                        )
                    ]
                )
                starts.append((version_index, change.new.start_line, lineage_index))
                current_owners[id(change.new)] = lineage_index
            else:
                assert change.old is not None
                lineage_index = owners[id(change.old)]
                lineages[lineage_index].append(
                    LineageEvent(
                        version.commit_sha,
                        change.kind,
                        change.new,
                    )
                )
                if change.new is not None:
                    current_owners[id(change.new)] = lineage_index

        baseline = current
        owners = current_owners

    order = sorted(range(len(lineages)), key=lambda index: starts[index])
    return FileHistory(
        lineages=tuple(SymbolLineage(tuple(lineages[index])) for index in order),
        skipped_commits=tuple(skipped),
    )
