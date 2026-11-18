from io import BytesIO

import pandas as pd
import pytest

from analyzer.loader import DatasetLoader, DatasetValidationError
from analyzer.web import DatasetWebApp


def test_loader_rejects_file_over_size_limit():
    with pytest.raises(DatasetValidationError, match="5 МБ"):
        DatasetLoader().load("large.csv", b"x" * (DatasetLoader.MAX_FILE_BYTES + 1))


def test_loader_rejects_more_than_max_rows():
    content = ("value\n" + "1\n" * (DatasetLoader.MAX_ROWS + 1)).encode("ascii")
    with pytest.raises(DatasetValidationError, match="строк"):
        DatasetLoader().load("many.csv", content)


def test_loader_rejects_more_than_max_columns():
    columns = ",".join(f"c{i}" for i in range(DatasetLoader.MAX_COLUMNS + 1))
    values = ",".join("1" for _ in range(DatasetLoader.MAX_COLUMNS + 1))
    with pytest.raises(DatasetValidationError, match="столбцов"):
        DatasetLoader().load("wide.csv", f"{columns}\n{values}\n".encode())


def test_wsgi_rejects_oversized_request_before_reading_body():
    app = DatasetWebApp()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/analyze",
        "QUERY_STRING": "",
        "CONTENT_TYPE": "multipart/form-data; boundary=x",
        "CONTENT_LENGTH": str(app.MAX_REQUEST_BYTES + 1),
        "wsgi.input": BytesIO(b"x"),
        "wsgi.errors": BytesIO(),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "SERVER_PROTOCOL": "HTTP/1.1",
    }
    result = {}
    def start_response(status, headers, exc_info=None):
        result["status"] = status
    body = b"".join(app(environ, start_response))
    assert result["status"].startswith("413")
    assert "превышает" in body.decode("utf-8")
