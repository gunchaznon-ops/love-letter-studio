#!/usr/bin/env python3
"""Love Letter Studio server (ไม่ต้องลงแพ็กเกจเพิ่ม ใช้ Python ล้วน)
รัน:  python server.py [port]      (ค่าเริ่มต้น 8080)
"""
import json, os, re, secrets, socket, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
MAX_BYTES = 60 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9]{6,12}$")
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TTL = 20 * 60                      # ลิงก์ใช้ได้ 20 นาที
OWNER_RE = re.compile(r"^[A-Za-z0-9]{16,64}$")
LOCK = threading.Lock()


def meta_path(lid):
    return os.path.join(DATA, lid + ".meta")


def remove_letter(lid):
    for ext in (".json", ".meta"):
        try:
            os.remove(os.path.join(DATA, lid + ext))
        except OSError:
            pass


def alive(lid):
    """คืน meta ถ้าจดหมายยังไม่หมดอายุ ไม่งั้นลบทิ้งแล้วคืน None"""
    try:
        with open(meta_path(lid), encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        return None
    if m.get("exp", 0) <= time.time():
        remove_letter(lid)
        return None
    return m


def find_active(owner):
    for fn in os.listdir(DATA):
        if fn.endswith(".meta"):
            lid = fn[:-5]
            m = alive(lid)
            if m and m.get("owner") == owner:
                return lid, m
    return None


def cleaner():
    while True:
        time.sleep(30)
        try:
            names = os.listdir(DATA)
            for fn in names:
                if fn.endswith(".meta"):
                    alive(fn[:-5])
            for fn in names:  # ไฟล์ค้างที่ไม่มี meta (เช่นของเก่าก่อนมีระบบหมดอายุ)
                if fn.endswith(".json") and not os.path.exists(meta_path(fn[:-5])):
                    try:
                        os.remove(os.path.join(DATA, fn))
                    except OSError:
                        pass
        except Exception:
            pass


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
        if path == "/api/status":
            owner = self.headers.get("X-Owner", "")
            if OWNER_RE.match(owner):
                with LOCK:
                    a = find_active(owner)
                if a:
                    lid, m = a
                    return self._send(200, json.dumps(
                        {"active": True, "id": lid, "remaining": max(1, int(m["exp"] - time.time()))}))
            return self._send(200, '{"active":false}')
        if path.startswith("/api/letter/"):
            lid = path.rsplit("/", 1)[-1]
            fp = os.path.join(DATA, lid + ".json")
            if ID_RE.match(lid) and alive(lid) and os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read())
            return self._send(404, '{"error":"not found"}')
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        owner = self.headers.get("X-Owner", "")
        if not OWNER_RE.match(owner):
            return self._send(400, '{"error":"ไม่พบรหัสผู้ใช้ ลองรีเฟรชหน้าเว็บ"}')
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._send(413, '{"error":"ไฟล์ใหญ่เกินไป (สูงสุด 60MB)"}')
        try:
            cfg = json.loads(self.rfile.read(n))
            if not isinstance(cfg, dict):
                raise ValueError
        except Exception:
            return self._send(400, '{"error":"ข้อมูลไม่ถูกต้อง"}')

        if self.path == "/api/delete":
            lid = str(cfg.get("id", ""))
            with LOCK:
                m = alive(lid) if ID_RE.match(lid) else None
                if m and m.get("owner") == owner:
                    remove_letter(lid)
                    return self._send(200, '{"ok":true}')
            return self._send(404, '{"error":"ไม่พบลิงก์นี้ (อาจหมดอายุแล้ว)"}')

        if self.path != "/api/save":
            return self._send(404, '{"error":"not found"}')

        with LOCK:
            a = find_active(owner)
            if a:
                lid, m = a
                return self._send(409, json.dumps({
                    "error": "มีลิงก์ที่ยังใช้งานอยู่ ต้องรอหมดเวลาหรือลบก่อน",
                    "id": lid, "remaining": max(1, int(m["exp"] - time.time()))}))
            while True:
                lid = "".join(secrets.choice(ALPHABET) for _ in range(8))
                if not os.path.exists(meta_path(lid)):
                    break
            with open(meta_path(lid), "w", encoding="utf-8") as f:   # เขียน meta ก่อน
                json.dump({"owner": owner, "exp": time.time() + TTL}, f)
            tmp = os.path.join(DATA, lid + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(DATA, lid + ".json"))
        self._send(200, json.dumps({"id": lid, "remaining": TTL}))

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
    threading.Thread(target=cleaner, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
