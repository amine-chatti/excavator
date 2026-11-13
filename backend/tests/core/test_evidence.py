from __future__ import annotations

import pytest

from excavator.core.evidence import (
    EvidenceLevel,
    EpistemicLabel,
    label_for_level,
    validate_quote,
)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (EvidenceLevel.DIRECT, EpistemicLabel.VERIFIED),
        (EvidenceLevel.STRONG, EpistemicLabel.VERIFIED),
        (EvidenceLevel.REFERENCED, EpistemicLabel.VERIFIED),
        (EvidenceLevel.MENTIONED, EpistemicLabel.INFERRED),
    ],
)
def test_label_for_level(level: EvidenceLevel, expected: EpistemicLabel) -> None:
    assert label_for_level(level) is expected


@pytest.mark.parametrize(
    ("source_text", "start", "end", "quote"),
    [
        ("Unicode café\nsecond line", 8, 12, "café"),
        ("first line\nsecond line", 0, 10, "first line"),
        ("first line\nsecond line", 11, 22, "second line"),
    ],
)
def test_validate_quote_accepts_exact_unicode_and_newline_slices(
    source_text: str,
    start: int,
    end: int,
    quote: str,
) -> None:
    assert validate_quote(source_text, start, end, quote)


@pytest.mark.parametrize(
    ("start", "end", "quote"),
    [
        (-1, 4, "text"),
        (0, 0, ""),
        (4, 2, "te"),
        (0, 5, "text"),
        (0, 4, "TEXT"),
    ],
)
def test_validate_quote_rejects_invalid_offsets_or_quote(
    start: int,
    end: int,
    quote: str,
) -> None:
    assert not validate_quote("text", start, end, quote)
