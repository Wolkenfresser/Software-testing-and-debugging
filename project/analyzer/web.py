from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from html import escape
from io import BytesIO
from urllib.parse import parse_qs

import pandas as pd

from .loader import DatasetLoader, DatasetValidationError
from .repository import DatasetRepository
from .service import AnalysisError, DatasetAnalyzer


PAGE_START = """<!doctype html>
<html lang=\"ru\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>DataLens Lab — анализ набора данных</title>
<style>
:root{font-family:Arial,Helvetica,sans-serif;color:#202938;background:#f3f5f8}*{box-sizing:border-box}
body{margin:0}.wrap{max-width:1100px;margin:0 auto;padding:32px 20px 60px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:26px}
.brand{font-size:22px;font-weight:700;letter-spacing:-.5px}.tag{color:#64748b;font-size:13px}.panel{background:#fff;border:1px solid #e4e8ef;border-radius:14px;padding:22px;margin:16px 0;box-shadow:0 4px 20px rgba(15,23,42,.035)}
h1{font-size:30px;margin:0 0 10px;letter-spacing:-.8px}h2{font-size:19px;margin:0 0 16px}p{line-height:1.55;color:#586579}.muted{color:#718096;font-size:13px}
label{display:block;font-size:13px;font-weight:700;margin:13px 0 6px}input{width:100%;padding:11px 12px;border:1px solid #cbd3df;border-radius:8px;font:inherit;background:#fff}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.btn{display:inline-block;border:0;border-radius:8px;background:#234e70;color:white;padding:12px 18px;font-weight:700;text-decoration:none;cursor:pointer;margin-top:18px}
.btn.secondary{background:#edf2f7;color:#234e70}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{background:#f7f9fc;border:1px solid #e7ebf2;border-radius:10px;padding:15px}.metric strong{font-size:25px;display:block;margin-top:5px}.metric span{font-size:12px;color:#718096}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid #edf0f4;overflow-wrap:anywhere}th{background:#f7f9fc;color:#465366;font-weight:700}
.table-wrap{overflow-x:auto}.notice{padding:13px 15px;border-radius:9px;background:#fff4e5;border:1px solid #f4d4a5;color:#79501b;margin:15px 0}.ok{background:#ecfdf3;border-color:#b7e4c7;color:#17663a}
footer{color:#8792a2;font-size:12px;margin-top:25px}.section-note{font-size:13px;color:#718096}
@media(max-width:700px){.grid,.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.top{align-items:flex-start;flex-direction:column}h1{font-size:25px}}
@media(max-width:420px){.grid,.metrics{grid-template-columns:1fr}.wrap{padding:22px 12px 40px}.panel{padding:16px}}
</style></head><body><main class=\"wrap\"><div class=\"top\"><div class=\"brand\">DataLens Lab</div><div class=\"tag\">Лабораторная работа · Вариант 13</div></div>"""
PAGE_END = "<footer>Учебный прототип. Файлы обрабатываются в памяти и не сохраняются на диск.</footer></main></body></html>"


class DatasetWebApp:
    """WSGI web application implemented with the Python standard library."""

    MAX_REQUEST_BYTES = 5 * 1024 * 1024 + 256 * 1024

    def __init__(
        self,
        loader: DatasetLoader | None = None,
        analyzer: DatasetAnalyzer | None = None,
        repository: DatasetRepository | None = None,
    ) -> None:
        self.loader = loader or DatasetLoader()
        self.analyzer = analyzer or DatasetAnalyzer()
        self.repository = repository or DatasetRepository()

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        try:
            if method == "GET" and path in ("/", "/index.html"):
                return self._send(start_response, "200 OK", self._index())
            if method == "GET" and path == "/health":
                return self._send(start_response, "200 OK", json.dumps({"status": "ok"}), "application/json; charset=utf-8")
            if method == "GET" and path.startswith("/download/"):
                return self._download(path.rsplit("/", 1)[-1], start_response)
            if method == "POST" and path == "/analyze":
                return self._analyze(environ, start_response)
            return self._send(start_response, "404 Not Found", self._page("<section class='panel'><h1>Страница не найдена</h1><a class='btn' href='/'>На главную</a></section>"))
        except Exception:
            # Do not disclose stack traces, file paths, or internal implementation details to clients.
            return self._send(start_response, "500 Internal Server Error", self._error_page("Внутренняя ошибка обработки запроса."))

    def _analyze(self, environ, start_response):
        try:
            content_length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return self._send(start_response, "400 Bad Request", self._error_page("Некорректный размер запроса."))
        if content_length <= 0:
            return self._send(start_response, "400 Bad Request", self._error_page("Файл для анализа не выбран."))
        if content_length > self.MAX_REQUEST_BYTES:
            return self._send(start_response, "413 Payload Too Large", self._error_page("Размер запроса превышает допустимое значение."))

        body = environ["wsgi.input"].read(content_length)
        try:
            fields, uploaded = self._parse_form(body, environ.get("CONTENT_TYPE", ""))
            if uploaded is None:
                raise DatasetValidationError("Файл для анализа не выбран.")
            filename, content = uploaded
            frame = self.loader.load(filename, content)
            filter_column = fields.get("filter_column", "").strip() or None
            min_value = self._optional_float(fields.get("min_value", ""), "Минимальная граница")
            max_value = self._optional_float(fields.get("max_value", ""), "Максимальная граница")
            filtered, report = self.analyzer.analyze(
                frame,
                title=filename,
                filter_column=filter_column,
                min_value=min_value,
                max_value=max_value,
            )
            token = self.repository.save(filename, filtered)
            html = self._report_page(report, token)
            return self._send(start_response, "200 OK", html)
        except (DatasetValidationError, AnalysisError) as exc:
            return self._send(start_response, "400 Bad Request", self._error_page(str(exc)))
        except Exception:
            return self._send(start_response, "400 Bad Request", self._error_page("Не удалось обработать набор данных. Проверьте файл и параметры фильтра."))

    @staticmethod
    def _optional_float(value: str, label: str) -> float | None:
        if value is None or not value.strip():
            return None
        try:
            result = float(value.strip().replace(",", "."))
        except ValueError as exc:
            raise AnalysisError(f"{label}: введите число.") from exc
        return result

    @staticmethod
    def _parse_form(body: bytes, content_type: str) -> tuple[dict[str, str], tuple[str, bytes] | None]:
        if content_type.lower().startswith("multipart/form-data"):
            header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
            message = BytesParser(policy=policy.default).parsebytes(header + body)
            fields: dict[str, str] = {}
            uploaded = None
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if not name:
                    continue
                payload = part.get_payload(decode=True) or b""
                filename = part.get_filename()
                if filename is not None and name == "file":
                    uploaded = (filename, payload)
                else:
                    charset = part.get_content_charset() or "utf-8"
                    fields[name] = payload.decode(charset, errors="replace")
            return fields, uploaded
        if content_type.lower().startswith("application/x-www-form-urlencoded"):
            values = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
            return {key: value[-1] for key, value in values.items()}, None
        raise DatasetValidationError("Ожидается форма multipart/form-data.")

    def _download(self, token: str, start_response):
        item = self.repository.get(token)
        if item is None:
            return self._send(start_response, "404 Not Found", self._error_page("Результат больше недоступен. Загрузите файл повторно."))
        filename, frame = item
        export = frame.copy()
        for column in export.columns:
            if pd.api.types.is_object_dtype(export[column]) or pd.api.types.is_string_dtype(export[column]):
                export[column] = export[column].map(self._safe_csv_cell)
        stream = BytesIO()
        export.to_csv(stream, index=False, encoding="utf-8-sig")
        data = stream.getvalue()
        safe_name = "filtered_dataset.csv"
        headers = [
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Length", str(len(data))),
            ("Content-Disposition", f'attachment; filename="{safe_name}"'),
            ("X-Content-Type-Options", "nosniff"),
            ("Cache-Control", "no-store"),
        ]
        start_response("200 OK", headers)
        return [data]

    @staticmethod
    def _safe_csv_cell(value):
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
            return "'" + value
        return value

    def _index(self) -> str:
        content = """<section class='panel'><h1>Интерактивный анализ набора данных</h1>
<p>Загрузите таблицу, изучите структуру данных, пропуски и описательные статистики. При необходимости примените числовой фильтр и скачайте полученную выборку.</p>
<form action='/analyze' method='post' enctype='multipart/form-data'>
<label for='file'>Файл данных (CSV или XLSX)</label><input id='file' name='file' type='file' accept='.csv,.xlsx' required>
<div class='grid'><div><label for='filter_column'>Числовой столбец для фильтра (необязательно)</label><input id='filter_column' name='filter_column' placeholder='например, revenue'></div>
<div><label for='min_value'>Минимальное значение</label><input id='min_value' name='min_value' inputmode='decimal' placeholder='без ограничения'></div>
<div><label for='max_value'>Максимальное значение</label><input id='max_value' name='max_value' inputmode='decimal' placeholder='без ограничения'></div></div>
<button class='btn' type='submit'>Загрузить и проанализировать</button></form></section>
<section class='panel'><h2>Что показывает анализ</h2><div class='grid'><div><b>Структура</b><p class='muted'>Количество строк и столбцов, типы данных и уникальные значения.</p></div><div><b>Качество данных</b><p class='muted'>Пропущенные ячейки и доля заполненности столбцов.</p></div><div><b>Статистика</b><p class='muted'>Количество, среднее, медиана, минимум и максимум для числовых признаков.</p></div></div>
<p class='section-note'>Ограничения: до 5 МБ, 20 000 строк и 100 столбцов. Данные хранятся только в памяти процесса.</p></section>"""
        return self._page(content)

    def _report_page(self, report, token: str) -> str:
        metrics = (
            ("Строк после фильтра", report.rows),
            ("Столбцов", report.columns),
            ("Пропусков", report.missing_cells),
            ("Заполненность", f"{report.completeness_percent:.2f}%"),
        )
        metric_html = "".join(
            f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"
            for label, value in metrics
        )
        filter_html = "" if not report.filter_description else f"<div class='notice ok'>Применён фильтр: {escape(report.filter_description)}. Исходных строк: {report.original_rows}; после фильтра: {report.rows}.</div>"
        columns = self._table(
            ["Столбец", "Тип", "Пропуски", "Пропуски, %", "Уникальные"],
            [[c["name"], c["dtype"], c["missing"], c["missing_percent"], c["unique"]] for c in report.column_info],
        )
        if report.numeric_stats:
            stats = self._table(
                ["Числовой столбец", "Кол-во", "Среднее", "Медиана", "Мин.", "Макс."],
                [[s["name"], s["count"], self._fmt(s["mean"]), self._fmt(s["median"]), self._fmt(s["min"]), self._fmt(s["max"])] for s in report.numeric_stats],
            )
        else:
            stats = "<p class='muted'>Числовые столбцы не обнаружены.</p>"
        preview_headers = list(report.column_info[i]["name"] for i in range(len(report.column_info)))
        preview_rows = [[row.get(column, "") for column in preview_headers] for row in report.preview]
        preview = self._table(preview_headers, preview_rows) if preview_headers else ""
        if report.rows > len(report.preview):
            preview_note = f"<p class='muted'>Показаны первые {len(report.preview)} строк из {report.rows}.</p>"
        else:
            preview_note = f"<p class='muted'>Показано строк: {len(report.preview)}.</p>"
        content = f"""<section class='panel'><div class='muted'>Результат анализа</div><h1>{escape(report.title)}</h1>
{filter_html}<div class='metrics'>{metric_html}</div><p class='muted'>Исходный набор: {report.original_rows} строк. Расчёты выполнены для набора после применения фильтра.</p>
<a class='btn' href='/download/{escape(token)}'>Скачать результат CSV</a> <a class='btn secondary' href='/'>Новый анализ</a></section>
<section class='panel'><h2>Структура столбцов</h2><div class='table-wrap'>{columns}</div></section>
<section class='panel'><h2>Описательная статистика</h2><div class='table-wrap'>{stats}</div></section>
<section class='panel'><h2>Предварительный просмотр</h2>{preview_note}<div class='table-wrap'>{preview}</div></section>"""
        return self._page(content)

    @staticmethod
    def _fmt(value):
        return "—" if value is None else escape(str(value))

    @staticmethod
    def _table(headers, rows) -> str:
        if not headers:
            return "<p class='muted'>Нет данных для отображения.</p>"
        head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
        body = "".join(
            "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>"
            for row in rows
        )
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

    def _error_page(self, message: str) -> str:
        return self._page(f"<section class='panel'><div class='notice'>{escape(message)}</div><a class='btn' href='/'>Вернуться к загрузке</a></section>")

    @staticmethod
    def _page(content: str) -> str:
        return PAGE_START + content + PAGE_END

    @staticmethod
    def _send(start_response, status: str, body: str, content_type: str = "text/html; charset=utf-8"):
        data = body.encode("utf-8")
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(data))),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"),
            ("Cache-Control", "no-store"),
        ]
        start_response(status, headers)
        return [data]


def create_app() -> DatasetWebApp:
    return DatasetWebApp()
