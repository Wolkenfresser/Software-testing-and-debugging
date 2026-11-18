from tests.helpers import WSGIClient
from analyzer.web import create_app


def test_smoke_critical_pages_respond():
    client = WSGIClient(create_app())
    assert client.get("/")["status"].startswith("200")
    assert client.get("/health")["status"].startswith("200")


def test_system_workflow_upload_analyze_and_export():
    client = WSGIClient(create_app())
    csv = "city,population\nСтаврополь,550000\nПятигорск,145000\nКисловодск,130000\n".encode("utf-8")
    analysis = client.post_multipart(
        "/analyze",
        fields={"filter_column": "population", "min_value": "140000"},
        file=("cities.csv", csv),
    )
    assert analysis["status"].startswith("200")
    html = analysis["body"].decode("utf-8")
    assert "Ставрополь" in html and "Пятигорск" in html
    assert "Кисловодск" not in html
    token = html.split("/download/", 1)[1].split("'", 1)[0]
    exported = client.get(f"/download/{token}")
    assert exported["status"].startswith("200")
    assert "Ставрополь".encode("utf-8") in exported["body"]


def test_regression_filter_without_bounds_keeps_all_rows():
    client = WSGIClient(create_app())
    csv = b"metric\n1\n2\n3\n"
    response = client.post_multipart(
        "/analyze", fields={"filter_column": "metric"}, file=("metrics.csv", csv)
    )
    html = response["body"].decode("utf-8")
    assert response["status"].startswith("200")
    assert "Строк после фильтра" in html
    assert "Исходный набор: 3 строк" in html
