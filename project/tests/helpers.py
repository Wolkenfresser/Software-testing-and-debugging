from __future__ import annotations

import io
import uuid
from urllib.parse import urlencode


class WSGIClient:
    def __init__(self, app):
        self.app = app

    def get(self, path):
        return self._call("GET", path, b"", "")

    def post_multipart(self, path, fields=None, file=None):
        boundary = "----Variant13" + uuid.uuid4().hex
        chunks = []
        for name, value in (fields or {}).items():
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        if file is not None:
            filename, content = file
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
            )
            chunks.append(b"Content-Type: application/octet-stream\r\n\r\n")
            chunks.append(content)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        body = b"".join(chunks)
        return self._call("POST", path, body, f"multipart/form-data; boundary={boundary}")

    def _call(self, method, path, body, content_type):
        from urllib.parse import urlsplit
        split = urlsplit(path)
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": split.path,
            "QUERY_STRING": split.query,
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": io.StringIO(),
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "8000",
            "SERVER_PROTOCOL": "HTTP/1.1",
        }
        captured = {}
        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = dict(headers)
        response = b"".join(self.app(environ, start_response))
        captured["body"] = response
        return captured
