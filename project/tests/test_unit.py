from io import BytesIO

import pandas as pd
import pytest

from analyzer.loader import DatasetLoader, DatasetValidationError
from analyzer.repository import DatasetRepository
from analyzer.service import AnalysisError, DatasetAnalyzer


def test_loader_reads_utf8_csv():
    frame = DatasetLoader().load("sales.csv", "name,value\nA,10\nБ,20\n".encode("utf-8"))
    assert frame.shape == (2, 2)
    assert frame.iloc[1, 0] == "Б"


def test_loader_reads_xlsx():
    output = BytesIO()
    pd.DataFrame({"id": [1, 2], "value": [10.5, 20.5]}).to_excel(output, index=False)
    frame = DatasetLoader().load("table.xlsx", output.getvalue())
    assert frame.shape == (2, 2)
    assert frame["value"].tolist() == [10.5, 20.5]


def test_loader_rejects_corrupted_xlsx():
    with pytest.raises(DatasetValidationError, match="Не удалось прочитать"):
        DatasetLoader().load("broken.xlsx", b"not-an-xlsx")


def test_loader_rejects_unsupported_extension():
    with pytest.raises(DatasetValidationError, match="CSV и XLSX"):
        DatasetLoader().load("notes.txt", b"hello")


def test_loader_rejects_empty_file():
    with pytest.raises(DatasetValidationError, match="пуст"):
        DatasetLoader().load("empty.csv", b"")


def test_analyzer_calculates_statistics_and_missing_values():
    frame = pd.DataFrame({"score": [10, 20, None], "group": ["A", "B", "A"]})
    _, report = DatasetAnalyzer().analyze(frame, "scores.csv")
    assert report.rows == 3
    assert report.columns == 2
    assert report.missing_cells == 1
    assert report.completeness_percent == pytest.approx(83.33, abs=0.01)
    assert report.numeric_stats[0]["mean"] == 15
    assert report.numeric_stats[0]["median"] == 15


def test_analyzer_filters_inclusive_range():
    frame = pd.DataFrame({"value": [1, 2, 3, 4, 5]})
    filtered, report = DatasetAnalyzer().analyze(frame, filter_column="value", min_value=2, max_value=4)
    assert filtered["value"].tolist() == [2, 3, 4]
    assert report.filter_description == "value: от 2 до 4"


def test_analyzer_rejects_unknown_filter_column():
    with pytest.raises(AnalysisError, match="не найден"):
        DatasetAnalyzer().analyze(pd.DataFrame({"x": [1]}), filter_column="y")


def test_analyzer_rejects_non_numeric_filter_column():
    with pytest.raises(AnalysisError, match="только для числового"):
        DatasetAnalyzer().analyze(pd.DataFrame({"name": ["a", "b"]}), filter_column="name")


def test_analyzer_rejects_reversed_range():
    with pytest.raises(AnalysisError, match="не может быть больше"):
        DatasetAnalyzer().analyze(pd.DataFrame({"x": [1, 2]}), filter_column="x", min_value=5, max_value=1)


def test_repository_returns_copy_and_handles_missing_id():
    repository = DatasetRepository()
    original = pd.DataFrame({"x": [1, 2]})
    token = repository.save("data.csv", original)
    item = repository.get(token)
    assert item is not None
    item[1].loc[0, "x"] = 999
    assert repository.get(token)[1].loc[0, "x"] == 1
    assert repository.get("unknown") is None
