#!/usr/bin/env python3
"""Love Letter Studio server (ไม่ต้องลงแพ็กเกจเพิ่ม ใช้ Python ล้วน)
รัน:  python server.py [port]      (ค่าเริ่มต้น 8080)
"""
import json, os, re, secrets, socket, sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
MAX_BYTES = 60 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9]{6,12}$")
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", cache="no-store"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path.startswith("/l/"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path.startswith("/api/letter/"):
            lid = path.rsplit("/", 1)[-1]
            fp = os.path.join(DATA, lid + ".json")
            if ID_RE.match(lid) and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), cache="public, max-age=300")
            return self._send(404, '{"error":"not found"}')
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path != "/api/save":
            return self._send(404, '{"error":"not found"}')
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._send(413, '{"error":"ไฟล์ใหญ่เกินไป (สูงสุด 60MB)"}')
        try:
            cfg = json.loads(self.rfile.read(n))
            if not isinstance(cfg, dict):
                raise ValueError
        except Exception:
            return self._send(400, '{"error":"ข้อมูลไม่ถูกต้อง"}')
        lid = "".join(secrets.choice(ALPHABET) for _ in range(8))
        with open(os.path.join(DATA, lid + ".json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        self._send(200, json.dumps({"id": lid}))

    def log_message(self, *a):
        pass


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print("\n💌 Love Letter Studio พร้อมแล้ว")
    print(f"   เปิดในมือถือเครื่องนี้ : http://localhost:{port}")
    print(f"   เพื่อนใน Wi-Fi เดียวกัน : http://{lan_ip()}:{port}")
    print("   (กด Ctrl+C เพื่อหยุด)\n")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
