"""后台 API 服务：A1111 兼容 txt2img 接口（标准 Stable Diffusion WebUI API 格式）.

仅用标准库，无额外依赖；与主界面共用同一个 Generator（内部加锁串行生成）。

接口：
  POST /sdapi/v1/txt2img
    请求: {"prompt", "negative_prompt", "width", "height", "steps",
           "cfg_scale", "seed"(-1 随机), "sampler_name"(忽略)}
    响应: {"images": ["<base64 png>"], "info": "<json 字符串>"}
  GET  /                  -> {"status": "ok", "model_loaded": bool}
  GET  /sdapi/v1/options  -> 最小 options 响应（兼容部分客户端探测）
"""

from __future__ import annotations

import base64
import json
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional


class ApiServer:
    def __init__(
        self,
        generate_fn: Callable,
        loaded_fn: Callable[[], bool],
        log: Callable[[str], None],
    ) -> None:
        self._generate = generate_fn
        self._loaded = loaded_fn
        self._log = log
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port = 0

    @property
    def alive(self) -> bool:
        return self._httpd is not None

    def start(self, port: int) -> bool:
        if self.alive:
            return True
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", port), self._make_handler())
        except OSError as e:
            self._log(f"API 服务启动失败（端口 {port} 被占用?）: {e}")
            self._httpd = None
            return False
        self.port = port
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self._log(f"API 服务已启动: http://127.0.0.1:{port}/sdapi/v1/txt2img （A1111 兼容格式）")
        return True

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._log(f"API 服务已停止（端口 {self.port}）")

    # ------------------------------------------------------------ handler
    def _make_handler(self):  # noqa: ANN202
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def _json(self, code: int, obj: dict) -> None:
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self) -> None:  # noqa: N802
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802
                if self.path in ("/", "/sdapi/v1/options", "/internal/ping"):
                    self._json(200, {"status": "ok", "model_loaded": server._loaded()})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/sdapi/v1/txt2img":
                    self._json(404, {"error": "not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception as e:
                    self._json(400, {"error": f"invalid json: {e}"})
                    return

                if not server._loaded():
                    self._json(503, {"error": "model not loaded（请先在软件中加载模型）"})
                    return

                seed = int(payload.get("seed", -1))
                if seed < 0:
                    seed = random.randint(0, 2**31 - 1)
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    self._json(400, {"error": "prompt is empty"})
                    return

                def noop(_p: float) -> None:
                    pass

                server._log(f"[API] txt2img: {prompt[:60]}...")
                path = server._generate(
                    prompt=prompt,
                    negative_prompt=str(payload.get("negative_prompt", "")),
                    width=max(64, int(payload.get("width", 1024))) // 8 * 8,
                    height=max(64, int(payload.get("height", 1024))) // 8 * 8,
                    steps=max(1, int(payload.get("steps", 20))),
                    guidance=float(payload.get("cfg_scale", 4.0)),
                    seed=seed,
                    log=server._log,
                    progress=noop,
                )
                if not path:
                    self._json(500, {"error": "generation failed（详见软件日志）"})
                    return
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                self._json(200, {
                    "images": [b64],
                    "info": json.dumps({
                        "seed": seed,
                        "steps": int(payload.get("steps", 20)),
                        "cfg_scale": float(payload.get("cfg_scale", 4.0)),
                        "width": int(payload.get("width", 1024)),
                        "height": int(payload.get("height", 1024)),
                    }, ensure_ascii=False),
                })

            def log_message(self, fmt: str, *args: object) -> None:  # 静默默认访问日志
                pass

        return Handler


# ---------------------------------------------------------------- 全局单例
_api: Optional[ApiServer] = None


def api_running() -> bool:
    return _api is not None and _api.alive


def api_port() -> int:
    return _api.port if _api else 0


def start_api(port: int, generate_fn: Callable, loaded_fn: Callable[[], bool], log: Callable[[str], None]) -> bool:
    global _api
    if _api is None:
        _api = ApiServer(generate_fn, loaded_fn, log)
    return _api.start(port)


def stop_api(log: Callable[[str], None]) -> None:
    if _api:
        _api.stop()
