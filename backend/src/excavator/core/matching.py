"""Match extracted symbols between two file versions.

Matching is identity-first, then uses equal body hashes to identify renames and
moves. A symbol renamed and edited at the same time is reported as removed and
added because this module does not perform fuzzy or similarity matching.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from excavator.core.symbols import ExtractedSymbol


class ChangeKind(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    RENAMED = "renamed"
    MOVED = "moved"
    ADDED = "added"
    REMOVED = "removed"


@dataclass(frozen=True, slots=True)
class SymbolChange:
    kind: ChangeKind
    old: ExtractedSymbol | None
    new: ExtractedSymbol | None


def match_symbols(
    old: tuple[ExtractedSymbol, ...],
    new: tuple[ExtractedSymbol, ...],
) -> tuple[SymbolChange, ...]:
    """Return deterministic changes between two extracted-symbol snapshots."""
    old_order = _ordered_indexes(old)
    new_order = _ordered_indexes(new)
    available_old = set(range(len(old)))
    available_new = set(range(len(new)))
    changes: list[SymbolChange] = []

    new_by_identity: dict[tuple[object, str, int], list[int]] = {}
    for index in new_order:
        symbol = new[index]
        new_by_identity.setdefault(_identity(symbol), []).append(index)

    for old_index in old_order:
        candidates = new_by_identity.get(_identity(old[old_index]), [])
        match = next((index for index in candidates if index in available_new), None)
        if match is None:
            continue
        available_old.remove(old_index)
        available_new.remove(match)
        kind = (
            ChangeKind.UNCHANGED
            if old[old_index].body_hash == new[match].body_hash
            else ChangeKind.MODIFIED
        )
        changes.append(SymbolChange(kind, old[old_index], new[match]))

    old_groups = _group_remaining(old, available_old)
    new_groups = _group_remaining(new, available_new)
    for group_key in sorted(set(old_groups) & set(new_groups), key=str):
        old_indexes = old_groups[group_key]
        new_indexes = new_groups[group_key]
        for old_index, new_index in zip(old_indexes, new_indexes, strict=False):
            available_old.remove(old_index)
            available_new.remove(new_index)
            old_symbol = old[old_index]
            new_symbol = new[new_index]
            kind = (
                ChangeKind.RENAMED
                if old_symbol.parent_qualified_name == new_symbol.parent_qualified_name
                and old_symbol.name != new_symbol.name
                else ChangeKind.MOVED
            )
            changes.append(SymbolChange(kind, old_symbol, new_symbol))

    changes.extend(SymbolChange(ChangeKind.REMOVED, old[index], None) for index in available_old)
    changes.extend(SymbolChange(ChangeKind.ADDED, None, new[index]) for index in available_new)
    return tuple(sorted(changes, key=_change_sort_key))


def _identity(symbol: ExtractedSymbol) -> tuple[object, str, int]:
    return symbol.kind, symbol.qualified_name, symbol.occurrence_index


def _group_key(symbol: ExtractedSymbol) -> tuple[object, str]:
    return symbol.kind, symbol.body_hash


def _group_remaining(
    symbols: tuple[ExtractedSymbol, ...], indexes: set[int]
) -> dict[tuple[object, str], list[int]]:
    groups: dict[tuple[object, str], list[int]] = {}
    for index in indexes:
        groups.setdefault(_group_key(symbols[index]), []).append(index)
    for group in groups.values():
        group.sort(key=lambda index: _symbol_sort_key(symbols[index]))
    return groups


def _ordered_indexes(symbols: tuple[ExtractedSymbol, ...]) -> list[int]:
    return sorted(range(len(symbols)), key=lambda index: _symbol_sort_key(symbols[index]))


def _symbol_sort_key(symbol: ExtractedSymbol) -> tuple[object, ...]:
    return (
        symbol.start_line,
        symbol.def_line,
        symbol.end_line,
        symbol.kind.value,
        symbol.qualified_name,
        symbol.occurrence_index,
        symbol.name,
        symbol.parent_qualified_name or "",
        symbol.body_hash,
    )


def _change_sort_key(change: SymbolChange) -> tuple[object, ...]:
    symbol = change.new or change.old
    assert symbol is not None
    return (symbol.start_line, *_symbol_sort_key(symbol)[1:])
