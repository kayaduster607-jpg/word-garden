"""本地和 Docker 使用相同 WSGI 应用；--dev 仅供本机预览。"""
import argparse
from backend.database import initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    initialize()
    from backend.web import application
    print(f"Word Garden: http://{args.host}:{args.port}", flush=True)
    if args.dev:
        from wsgiref.simple_server import make_server
        with make_server(args.host, args.port, application) as server:
            server.serve_forever()
    else:
        from waitress import serve
        serve(application, host=args.host, port=args.port, threads=8,
              max_request_body_size=16384, channel_timeout=30,
              clear_untrusted_proxy_headers=False)


if __name__ == "__main__":
    main()
