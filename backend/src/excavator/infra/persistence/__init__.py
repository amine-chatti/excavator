"""Persistence services for core analysis results."""

from excavator.infra.persistence.file_history import PersistResult, persist_file_history

__all__ = ["PersistResult", "persist_file_history"]
