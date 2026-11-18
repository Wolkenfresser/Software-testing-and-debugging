from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from wsgiref.simple_server import make_server

from analyzer.web import create_app


def test_actual_http_server_serves_index_and_health():
    server = make_server("127.0.0.1", 0, create_app())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "DataLens Lab" in html
        with urlopen(base + "/health", timeout=3) as response:
            assert response.status == 200
            assert response.read() == b'{"status": "ok"}'
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_actual_http_server_accepts_multipart_csv_upload():
    server = make_server("127.0.0.1", 0, create_app())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    boundary = "----actual-http-boundary"
    csv = "name,value\nАльфа,10\nБета,20\n".encode("utf-8")
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="http.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode() + csv + f"\r\n--{boundary}--\r\n".encode()
    request = Request(
        base + "/analyze",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "http.csv" in html
            assert "Альфа" in html and "Бета" in html
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
