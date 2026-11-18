from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import math
import pandas as pd


class AnalysisError(ValueError):
    """Raised when a requested analysis or filter is invalid."""


@dataclass(frozen=True)
class AnalysisReport:
    title: str
    original_rows: int
    rows: int
    columns: int
    missing_cells: int
    completeness_percent: float
    column_info: list[dict[str, Any]]
    numeric_stats: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    numeric_columns: list[str]
    filter_description: str | None


class DatasetAnalyzer:
    PREVIEW_LIMIT = 15

    def analyze(
        self,
        frame: pd.DataFrame,
        title: str = "dataset",
        filter_column: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> tuple[pd.DataFrame, AnalysisReport]:
        if frame is None:
            raise AnalysisError("Набор данных не задан.")
        if len(frame.columns) == 0:
            raise AnalysisError("Набор данных не содержит столбцов.")

        filtered = frame.copy()
        filter_description = None
        if filter_column:
            if filter_column not in filtered.columns:
                raise AnalysisError("Указанный столбец фильтра не найден.")
            if not pd.api.types.is_numeric_dtype(filtered[filter_column]):
                raise AnalysisError("Фильтрация по диапазону доступна только для числового столбца.")
            if min_value is not None and not math.isfinite(min_value):
                raise AnalysisError("Минимальная граница должна быть конечным числом.")
            if max_value is not None and not math.isfinite(max_value):
                raise AnalysisError("Максимальная граница должна быть конечным числом.")
            if min_value is not None and max_value is not None and min_value > max_value:
                raise AnalysisError("Минимальная граница не может быть больше максимальной.")
            mask = pd.Series(True, index=filtered.index)
            if min_value is not None:
                mask &= filtered[filter_column] >= min_value
            if max_value is not None:
                mask &= filtered[filter_column] <= max_value
            filtered = filtered.loc[mask].copy()
            left = "−∞" if min_value is None else str(min_value)
            right = "+∞" if max_value is None else str(max_value)
            filter_description = f"{filter_column}: от {left} до {right}"

        rows, columns = filtered.shape
        missing_cells = int(filtered.isna().sum().sum())
        total_cells = rows * columns
        completeness = 100.0 if total_cells == 0 else (1 - missing_cells / total_cells) * 100

        column_info: list[dict[str, Any]] = []
        numeric_stats: list[dict[str, Any]] = []
        numeric_columns: list[str] = []
        for column in filtered.columns:
            series = filtered[column]
            missing = int(series.isna().sum())
            column_info.append(
                {
                    "name": str(column),
                    "dtype": str(series.dtype),
                    "missing": missing,
                    "missing_percent": round((missing / rows * 100), 2) if rows else 0.0,
                    "unique": int(series.nunique(dropna=True)),
                }
            )
            if pd.api.types.is_numeric_dtype(series):
                numeric_columns.append(str(column))
                clean = series.dropna()
                numeric_stats.append(
                    {
                        "name": str(column),
                        "count": int(clean.count()),
                        "mean": self._number(clean.mean()),
                        "median": self._number(clean.median()),
                        "min": self._number(clean.min()),
                        "max": self._number(clean.max()),
                    }
                )

        preview_frame = filtered.head(self.PREVIEW_LIMIT).astype(object).where(pd.notna(filtered.head(self.PREVIEW_LIMIT)), "")
        preview = [
            {str(key): self._display_value(value) for key, value in row.items()}
            for row in preview_frame.to_dict(orient="records")
        ]
        report = AnalysisReport(
            title=title,
            original_rows=len(frame),
            rows=rows,
            columns=columns,
            missing_cells=missing_cells,
            completeness_percent=round(completeness, 2),
            column_info=column_info,
            numeric_stats=numeric_stats,
            preview=preview,
            numeric_columns=numeric_columns,
            filter_description=filter_description,
        )
        return filtered, report

    @staticmethod
    def _number(value: Any) -> float | int | None:
        if pd.isna(value):
            return None
        number = float(value)
        return int(number) if number.is_integer() else round(number, 4)

    @staticmethod
    def _display_value(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
