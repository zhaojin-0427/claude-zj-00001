"""Flask 缺失时的零依赖回退实现（仅使用 Python 标准库）。

当容器/环境未能安装 Flask 时，app.py 自动改用本模块，对外暴露与 Flask
一致的最小子集：Flask 应用对象（get/post 路由、teardown_appcontext）、
g、request（args/get_json）、jsonify，以及一个 WSGI 单线程开发服务器。
路由规则支持 Flask 风格的 ``<int:id>`` / ``<name>`` 路径参数。
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class _G:
    """请求级全局对象（单线程服务器中每请求重置），支持 Flask 风格 pop/get"""
    def __contains__(self, key):
        return key in self.__dict__

    def pop(self, key, default=None):
        return self.__dict__.pop(key, default)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)


g = _G()


class _Args:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, key, default=None):
        v = self._m.get(key)
        if v is None:
            return default
        return v[0]


class _Request:
    def __init__(self):
        self.args = _Args({})
        self._json = None

    def get_json(self, force=False):
        return self._json


request = _Request()


class _Response:
    def __init__(self, payload):
        self.payload = payload


def jsonify(payload):
    return _Response(payload)


class _Rule:
    def __init__(self, rule, method, fn):
        self.rule = rule
        self.method = method
        self.fn = fn
        # /api/pets/<int:pet_id> / <plan_id> -> 命名正则（单次替换，避免二次命中）
        def _convert(m):
            name = m.group(2)
            fragment = "-?\\d+" if m.group(1) else "[^/]+"
            return "(?P<" + name + ">" + fragment + ")"

        pat = re.sub(r"<(?:(int):)?(\w+)>", _convert, rule)
        self.regex = re.compile("^" + pat + "$")
        self.int_args = set(re.findall(r"<int:(\w+)>", rule))


class Flask:
    def __init__(self, name):
        self.name = name
        self.rules = []
        self._teardowns = []

    def teardown_appcontext(self, fn):
        self._teardowns.append(fn)

    def _register(self, rule, method):
        def deco(fn):
            self.rules.append(_Rule(rule, method, fn))
            return fn
        return deco

    def get(self, rule):
        return self._register(rule, "GET")

    def post(self, rule):
        return self._register(rule, "POST")

    def run(self, host="0.0.0.0", port=5000, **kwargs):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _handle(self, method):
                parsed = urlparse(self.path)
                # 预检请求直接放行（等价于 flask_cors 的 CORS(*)）
                if method == "OPTIONS":
                    self.send_response(204)
                    self._cors()
                    self.end_headers()
                    return
                for rule in app.rules:
                    if rule.method != method:
                        continue
                    m = rule.regex.match(parsed.path)
                    if not m:
                        continue
                    kwargs = {k: (int(v) if k in rule.int_args else v)
                              for k, v in m.groupdict().items()}
                    # 每请求使用全新的 g（等价 Flask 新 app context）
                    g.__dict__.clear()
                    request.args = _Args(parse_qs(parsed.query))
                    request._json = self._read_json()
                    try:
                        result = rule.fn(**kwargs)
                    finally:
                        for td in app._teardowns:
                            td(None)
                    resp, status = self._normalize(result)
                    self._write(status, resp)
                    return
                self._write(404, {"error": "Not Found"})

            def _read_json(self):
                length = int(self.headers.get("Content-Length") or 0)
                if not length:
                    return None
                raw = self.rfile.read(length)
                if not raw:
                    return None
                try:
                    return json.loads(raw.decode("utf-8"))
                except Exception:
                    return None

            @staticmethod
            def _normalize(result):
                if isinstance(result, tuple):
                    resp = result[0]
                    status = result[1] if len(result) > 1 else 200
                else:
                    resp, status = result, 200
                if isinstance(resp, _Response):
                    return resp.payload, status
                return resp, status

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods",
                                 "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Content-Type, Authorization")

            def _write(self, status, payload):
                body = json.dumps(payload, ensure_ascii=False,
                                  default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type",
                                 "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_OPTIONS(self):
                self._handle("OPTIONS")

        server = HTTPServer((host, port), Handler)
        print(f" * 标准库回退服务器运行于 http://{host}:{port}（未安装 Flask）")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()


def CORS(app, **kwargs):
    return None
