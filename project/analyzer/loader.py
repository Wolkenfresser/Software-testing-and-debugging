from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd


class DatasetValidationError(ValueError):
    """Raised when an uploaded dataset does not satisfy input constraints."""


class DatasetLoader:
    ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
    MAX_FILE_BYTES = 5 * 1024 * 1024
    MAX_ROWS = 20_000
    MAX_COLUMNS = 100

    def load(self, filename: str, content: bytes) -> pd.DataFrame:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in self.ALLOWED_EXTENSIONS:
            raise DatasetValidationError("Поддерживаются только файлы CSV и XLSX.")
        if not content:
            raise DatasetValidationError("Загруженный файл пуст.")
        if len(content) > self.MAX_FILE_BYTES:
            raise DatasetValidationError("Размер файла превышает ограничение 5 МБ.")

        try:
            if suffix == ".csv":
                frame = self._read_csv(content)
            else:
                frame = pd.read_excel(BytesIO(content), engine="openpyxl")
        except DatasetValidationError:
            raise
        except Exception as exc:
            raise DatasetValidationError(
                "Не удалось прочитать файл. Проверьте формат и содержимое."
            ) from exc

        if frame.empty and len(frame.columns) == 0:
            raise DatasetValidationError("Файл не содержит таблицу с заголовками.")
        if len(frame.columns) == 0:
            raise DatasetValidationError("В таблице отсутствуют столбцы.")
        if len(frame) > self.MAX_ROWS:
            raise DatasetValidationError(
                f"Количество строк превышает ограничение {self.MAX_ROWS}."
            )
        if len(frame.columns) > self.MAX_COLUMNS:
            raise DatasetValidationError(
                f"Количество столбцов превышает ограничение {self.MAX_COLUMNS}."
            )

        # Normalize column labels without silently changing their meaning.
        normalized = []
        for index, value in enumerate(frame.columns):
            label = str(value).strip()
            normalized.append(label if label else f"column_{index + 1}")
        frame.columns = normalized
        if len(set(frame.columns)) != len(frame.columns):
            raise DatasetValidationError("Названия столбцов должны быть уникальными.")
        return frame

    @staticmethod
    def _read_csv(content: bytes) -> pd.DataFrame:
        errors = []
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                text = content.decode(encoding)
                first_line = next((line for line in text.splitlines() if line.strip()), "")
                # A one-column CSV has no separator to sniff; default to comma.
                has_separator = any(char in first_line for char in (",", ";", "\t", "|"))
                if has_separator:
                    return pd.read_csv(BytesIO(content), encoding=encoding, sep=None, engine="python")
                return pd.read_csv(BytesIO(content), encoding=encoding, sep=",")
            except Exception as exc:  # try the next supported encoding
                errors.append(exc)
        raise DatasetValidationError(
            "CSV не удалось прочитать в UTF-8 или Windows-1251. Проверьте разделитель и кодировку."
        ) from errors[-1]
