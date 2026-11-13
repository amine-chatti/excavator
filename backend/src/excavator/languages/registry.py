from __future__ import annotations

from pathlib import PurePath

from excavator.core.language import LanguageAnalyzer
from excavator.languages.python import PythonAnalyzer

_ANALYZERS: tuple[LanguageAnalyzer, ...] = (PythonAnalyzer(),)


def get_analyzer(path: str) -> LanguageAnalyzer | None:
    extension = PurePath(path).suffix.casefold()
    return next(
        (analyzer for analyzer in _ANALYZERS if extension in analyzer.file_extensions()),
        None,
    )
