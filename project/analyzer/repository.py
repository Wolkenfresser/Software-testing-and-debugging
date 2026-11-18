from __future__ import annotations

from threading import RLock
from uuid import uuid4

import pandas as pd


class DatasetRepository:
    """Small in-memory store used by the demo application; data is not persistent."""

    MAX_ITEMS = 8

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, pd.DataFrame]] = {}
        self._lock = RLock()

    def save(self, filename: str, frame: pd.DataFrame) -> str:
        token = uuid4().hex
        with self._lock:
            if len(self._items) >= self.MAX_ITEMS:
                oldest = next(iter(self._items))
                del self._items[oldest]
            self._items[token] = (filename, frame.copy())
        return token

    def get(self, token: str) -> tuple[str, pd.DataFrame] | None:
        with self._lock:
            item = self._items.get(token)
            if item is None:
                return None
            filename, frame = item
            return filename, frame.copy()

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
