from __future__ import annotations

from excavator.languages.python import PythonAnalyzer
from excavator.languages.registry import get_analyzer


def test_registry_resolves_python_case_insensitively() -> None:
    assert isinstance(get_analyzer("module.py"), PythonAnalyzer)
    assert isinstance(get_analyzer("MODULE.PY"), PythonAnalyzer)
    assert get_analyzer("module.js") is None
    assert get_analyzer("module") is None
