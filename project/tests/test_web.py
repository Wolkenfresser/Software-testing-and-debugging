from tests.helpers import WSGIClient
from analyzer.web import create_app


CSV = "id,region,revenue\n1,North,100\n2,South,250\n3,West,400\n".encode("utf-8")


def test_home_and_health_endpoints():
    client = WSGIClient(create_app())
    home = client.get("/")
    health = client.get("/health")
    assert home["status"].startswith("200")
    assert "Интерактивный анализ набора данных".encode("utf-8") in home["body"]
    assert health["status"].startswith("200")
    assert b'"status": "ok"' in health["body"]


def test_upload_analyze_filter_and_download_workflow():
    client = WSGIClient(create_app())
    response = client.post_multipart(
        "/analyze",
        fields={"filter_column": "revenue", "min_value": "200", "max_value": "400"},
        file=("sales.csv", CSV),
    )
    assert response["status"].startswith("200")
    assert "Строк после фильтра" in response["body"].decode("utf-8")
    assert b"North" not in response["body"]
    assert b"South" in response["body"]
    html = response["body"].decode("utf-8")
    token = html.split("/download/", 1)[1].split("'", 1)[0]
    downloaded = client.get(f"/download/{token}")
    assert downloaded["status"].startswith("200")
    assert b"South" in downloaded["body"]
    assert b"North" not in downloaded["body"]


def test_upload_rejects_unsupported_file():
    response = WSGIClient(create_app()).post_multipart(
        "/analyze", file=("malware.exe", b"not really an executable")
    )
    assert response["status"].startswith("400")
    assert "Поддерживаются только файлы CSV и XLSX" in response["body"].decode("utf-8")


def test_filename_is_html_escaped():
    response = WSGIClient(create_app()).post_multipart(
        "/analyze", file=('sales&report.csv', CSV)
    )
    html = response["body"].decode("utf-8")
    assert response["status"].startswith("200")
    assert 'sales&amp;report.csv' in html


def test_download_is_not_found_for_unknown_token():
    response = WSGIClient(create_app()).get("/download/unknown")
    assert response["status"].startswith("404")


def test_security_headers_are_present():
    response = WSGIClient(create_app()).get("/")
    assert response["headers"]["X-Content-Type-Options"] == "nosniff"
    assert response["headers"]["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response["headers"]


def test_export_neutralizes_formula_prefixes():
    app = create_app()
    client = WSGIClient(app)
    csv = b"label,value\n=1+1,10\n"
    response = client.post_multipart("/analyze", file=("formula.csv", csv))
    token = response["body"].decode("utf-8").split("/download/", 1)[1].split("'", 1)[0]
    exported = client.get(f"/download/{token}")
    assert b"'=1+1" in exported["body"]
