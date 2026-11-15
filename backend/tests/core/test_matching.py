from __future__ import annotations

from itertools import permutations

from excavator.core.matching import ChangeKind, SymbolChange, match_symbols
from excavator.core.symbols import ExtractedSymbol, SymbolKind


def symbol(
    name: str,
    *,
    kind: SymbolKind = SymbolKind.FUNCTION,
    qualified_name: str | None = None,
    parent: str | None = None,
    line: int = 1,
    occurrence: int = 0,
    body_hash: str = "same",
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


def kinds(changes: tuple[SymbolChange, ...]) -> list[ChangeKind]:
    return [change.kind for change in changes]


def test_empty_inputs() -> None:
    assert match_symbols((), ()) == ()


def test_all_added_and_all_removed() -> None:
    added = symbol("new", line=2)
    removed = symbol("old", line=1)

    assert kinds(match_symbols((), (added,))) == [ChangeKind.ADDED]
    assert kinds(match_symbols((removed,), ())) == [ChangeKind.REMOVED]


def test_identical_and_modified_symbols() -> None:
    unchanged = symbol("same", line=1, body_hash="a")
    modified = symbol("changed", line=2, body_hash="b")
    modified_new = symbol("changed", line=2, body_hash="c")

    changes = match_symbols((unchanged, modified), (unchanged, modified_new))

    assert kinds(changes) == [ChangeKind.UNCHANGED, ChangeKind.MODIFIED]
    assert changes[0].old == unchanged
    assert changes[1].new == modified_new


def test_rename_and_move_require_identical_body() -> None:
    renamed_old = symbol("old", qualified_name="old", line=1, body_hash="a")
    renamed_new = symbol("new", qualified_name="new", line=1, body_hash="a")
    moved_old = symbol(
        "method",
        qualified_name="A.method",
        parent="A",
        line=2,
        body_hash="b",
    )
    moved_new = symbol(
        "method",
        qualified_name="B.method",
        parent="B",
        line=2,
        body_hash="b",
    )

    changes = match_symbols(
        (renamed_old, moved_old),
        (renamed_new, moved_new),
    )

    assert kinds(changes) == [ChangeKind.RENAMED, ChangeKind.MOVED]


def test_renamed_and_edited_is_removed_and_added() -> None:
    old = symbol("old", qualified_name="old", body_hash="old", line=1)
    new = symbol("new", qualified_name="new", body_hash="new", line=2)

    assert kinds(match_symbols((old,), (new,))) == [
        ChangeKind.REMOVED,
        ChangeKind.ADDED,
    ]


def test_duplicate_occurrences_pair_by_identity_and_middle_addition() -> None:
    old = (
        symbol("x", qualified_name="A.x", parent="A", occurrence=0, line=1, body_hash="a"),
        symbol("x", qualified_name="A.x", parent="A", occurrence=1, line=2, body_hash="b"),
    )
    new = (
        old[0],
        symbol("x", qualified_name="A.x", parent="A", occurrence=1, line=2, body_hash="new"),
        symbol("x", qualified_name="A.x", parent="A", occurrence=2, line=3, body_hash="b"),
    )

    changes = match_symbols(old, new)

    assert kinds(changes) == [
        ChangeKind.UNCHANGED,
        ChangeKind.MODIFIED,
        ChangeKind.ADDED,
    ]
    assert changes[2].new == new[2]


def test_same_hash_duplicate_removed_and_added_pair_in_source_order() -> None:
    old = (
        symbol("old_one", line=1, body_hash="same"),
        symbol("old_two", line=2, body_hash="same"),
    )
    new = (
        symbol("new_one", line=3, body_hash="same"),
        symbol("new_two", line=4, body_hash="same"),
    )

    changes = match_symbols(old, new)

    assert kinds(changes) == [ChangeKind.RENAMED, ChangeKind.RENAMED]
    pairs = [
        (change.old, change.new)
        for change in changes
        if change.old is not None and change.new is not None
    ]
    assert [(old_symbol.name, new_symbol.name) for old_symbol, new_symbol in pairs] == [
        ("old_one", "new_one"),
        ("old_two", "new_two"),
    ]


def test_same_name_different_kind_is_not_matched() -> None:
    old = symbol("thing", kind=SymbolKind.CLASS, body_hash="same")
    new = symbol("thing", kind=SymbolKind.FUNCTION, body_hash="same")

    assert kinds(match_symbols((old,), (new,))) == [
        ChangeKind.REMOVED,
        ChangeKind.ADDED,
    ]


def test_duplicate_exact_identity_is_matched_only_once() -> None:
    old = (
        symbol("f", qualified_name="f", occurrence=0, line=1),
        symbol("f", qualified_name="f", occurrence=0, line=2),
    )
    new = (old[0],)

    changes = match_symbols(old, new)

    assert kinds(changes) == [ChangeKind.UNCHANGED, ChangeKind.REMOVED]


def test_determinism_under_input_shuffling() -> None:
    old = (
        symbol("old_a", line=1, body_hash="same"),
        symbol("old_b", line=2, body_hash="same"),
        symbol("removed", line=5, body_hash="gone"),
    )
    new = (
        symbol("new_a", line=3, body_hash="same"),
        symbol("new_b", line=4, body_hash="same"),
        symbol("added", line=6, body_hash="new"),
    )
    expected = match_symbols(old, new)

    for old_permutation in permutations(old):
        for new_permutation in permutations(new):
            assert match_symbols(old_permutation, new_permutation) == expected


def test_every_input_symbol_appears_exactly_once() -> None:
    old = (
        symbol("kept", line=1),
        symbol("removed", line=2),
    )
    new = (
        symbol("kept", line=1),
        symbol("added", line=3),
    )

    changes = match_symbols(old, new)

    old_symbols = [change.old for change in changes if change.old is not None]
    new_symbols = [change.new for change in changes if change.new is not None]
    assert old_symbols.count(old[0]) == 1
    assert old_symbols.count(old[1]) == 1
    assert new_symbols.count(new[0]) == 1
    assert new_symbols.count(new[1]) == 1
