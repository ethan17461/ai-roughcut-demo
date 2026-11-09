"""本地工作台：在浏览器里输入选题 → 现场跑流水线 → 预览 → 换镜头 → 写回剪映草稿。

用法：.venv/bin/python studio.py   然后打开 http://localhost:8770
API key 放在 .env（DeepSeek 写脚本，MiniMax 配音），只在本机用，不会进网页。
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import llm

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output")
PORT = int(os.environ.get("PORT", 8770))
job = {"running": False, "log": [], "error": None}
lock = threading.Lock()


def page():
    tpl = open(os.path.join(ROOT, "web", "template.html"), encoding="utf-8").read()
    result = open(os.path.join(OUT, "result.json"), encoding="utf-8").read()
    return tpl.replace("/*__RESULT__*/null", result).replace("/*__STUDIO__*/false", "true")


def run_pipeline(args):
    """后台跑 pipeline.py，把每一步的日志收进 job，网页轮询 /api/status 显示真实进度。"""
    cmd = [sys.executable, "-u", os.path.join(ROOT, "pipeline.py")] + args
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        tail = (tail + [line])[-15:]
        if "｜" in line and line.startswith("["):
            ms, rest = line[1:].split("]", 1)
            step, msg = rest.strip().split("｜", 1)
            with lock:
                job["log"].append({"step": step, "msg": msg, "ms": int(ms.replace("ms", "").strip())})
    p.wait()
    with lock:
        job["running"] = False
        if p.returncode != 0:
            err = next((l for l in reversed(tail) if "Error" in l or "错误" in l or "key" in l), tail[-1] if tail else "未知错误")
            job["error"] = err


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            return self._send(200, page(), "text/html; charset=utf-8")
        if path == "/api/status":
            with lock:
                return self._send(200, dict(job))
        if path == "/api/keys":
            return self._send(200, {"deepseek": llm.has("DEEPSEEK_API_KEY"), "minimax": llm.has("MINIMAX_API_KEY")})
        # 静态文件：clips/、thumbs/；audio/ 直接读 output/tts/（每次生成都是新的）
        if path.startswith("/audio/"):
            f = os.path.join(OUT, "tts", os.path.basename(path))
        elif path.startswith(("/clips/", "/thumbs/")):
            f = os.path.join(ROOT, path.lstrip("/"))
        else:
            return self._send(404, {"error": "not found"})
        if not os.path.isfile(f):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
        size = os.path.getsize(f)
        rng = self.headers.get("Range")
        with open(f, "rb") as fh:
            if rng and rng.startswith("bytes="):  # 视频拖动需要分段读取
                a, _, b = rng[6:].partition("-")
                a = int(a or 0)
                b = int(b) if b else size - 1
                fh.seek(a)
                data = fh.read(b - a + 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            else:
                data = fh.read()
                self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/run":
            body = self._json()
            topic = (body.get("topic") or "").strip()[:80]
            if not topic:
                return self._send(400, {"error": "请先输入选题"})
            if not llm.has("DEEPSEEK_API_KEY"):
                return self._send(400, {"error": "还没填 DeepSeek key：请在 .env 里填 DEEPSEEK_API_KEY"})
            with lock:
                if job["running"]:
                    return self._send(409, {"error": "上一个还在生成"})
                job.update(running=True, log=[], error=None)
            args = ["--topic", topic, "--market", body.get("market") or "英国", "--platform", body.get("platform") or "TikTok"]
            threading.Thread(target=run_pipeline, args=(args,), daemon=True).start()
            return self._send(200, {"ok": True})
        if path == "/api/redraft":
            swaps = self._json().get("swaps") or {}
            sp = os.path.join(OUT, "swaps.json")
            json.dump(swaps, open(sp, "w"), ensure_ascii=False)
            r = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline.py"), "--redraft", sp], cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                return self._send(500, {"error": (r.stderr or r.stdout)[-400:]})
            return self._send(200, {"ok": True, "msg": r.stdout.strip()})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"AI 粗剪工作台：http://localhost:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
