from __future__ import annotations

import ast
from pathlib import Path

CORE_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "excavator" / "core"
FORBIDDEN_MODULES = {
    "excavator.api",
    "excavator.infra",
    "fastapi",
    "sqlalchemy",
}


def _iter_python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if path.is_file())


def test_core_does_not_import_forbidden_modules() -> None:
    violations: list[str] = []

    for file_path in _iter_python_files(CORE_PACKAGE):
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (
                        alias.name in FORBIDDEN_MODULES
                        or alias.name.startswith("fastapi.")
                        or alias.name.startswith("sqlalchemy.")
                    ):
                        violations.append(f"{file_path}:{node.lineno}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                if (
                    module_name in FORBIDDEN_MODULES
                    or module_name.startswith("excavator.api")
                    or module_name.startswith("excavator.infra")
                ):
                    violations.append(f"{file_path}:{node.lineno}: imports {module_name}")
                if (
                    any(alias.name in {"api", "infra"} for alias in node.names)
                    and module_name == "excavator"
                ):
                    imported_name = next(
                        alias.name for alias in node.names if alias.name in {"api", "infra"}
                    )
                    violations.append(
                        f"{file_path}:{node.lineno}: imports excavator.{imported_name}"
                    )

    assert not violations, "Forbidden imports found in core package:\n" + "\n".join(violations)
