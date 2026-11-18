from wsgiref.simple_server import make_server

from analyzer import create_app


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    app = create_app()
    print(f"DataLens Lab запущен: http://{host}:{port}")
    print("Для остановки нажмите Ctrl+C")
    with make_server(host, port, app) as server:
        server.serve_forever()
