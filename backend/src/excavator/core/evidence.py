from __future__ import annotations

from enum import StrEnum


class EvidenceLevel(StrEnum):
    DIRECT = "direct"
    STRONG = "strong"
    REFERENCED = "referenced"
    MENTIONED = "mentioned"


class EpistemicLabel(StrEnum):
    VERIFIED = "verified"
    INFERRED = "inferred"


def label_for_level(level: EvidenceLevel) -> EpistemicLabel:
    if level is EvidenceLevel.MENTIONED:
        return EpistemicLabel.INFERRED
    return EpistemicLabel.VERIFIED


def validate_quote(source_text: str, start: int, end: int, quote: str) -> bool:
    return 0 <= start < end <= len(source_text) and source_text[start:end] == quote
