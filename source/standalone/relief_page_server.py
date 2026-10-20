"""Local-only Mountain relief editor and Apply service. Never launches Rally."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import base64
import json
import secrets
import threading
import webbrowser
from relief_apply import ROOT, YAML, RECEIPT, revision, load, apply, allowed_variants

class App:
    def __init__(self, root=ROOT):
        self.root = root
        page = (root / "scratchpad/pom-depth-tuner-20261020/index.html").read_text(encoding="utf-8")
        start = page.index("const inventory=") + len("const inventory=")
        inventory, length = json.JSONDecoder().raw_decode(page[start:])
        self.assets = {}
        for item in inventory["items"]:
            for kind in ("albedo", "packed"):
                uri = "/asset/" + item["id"] + "/" + kind + ".png"
                self.assets[uri] = base64.b64decode(item[kind].split(",", 1)[1])
                item[kind] = uri
        self.page = (page[:start] + json.dumps(inventory) + page[start+length:]).replace(
            "</html>", '<script src="/apply.js"></script></html>').encode()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.job = {"state": "idle", "message": ""}
    def settings(self):
        config = load(self.root / YAML)
        return {"token": self.token, "revision": revision(self.root), "families": config["families"],
                "excluded_variants": config["excluded_variants"], "allowed_variants": allowed_variants(self.root),
                "global_depth_initial": float(config["global_depth_initial"]), "live_tuner": config["live_tuner"] == "true",
                "audit": json.loads((self.root / RECEIPT).read_text())["material_audit"]}
    def start(self, payload):
        if not self.lock.acquire(blocking=False): raise ValueError("An Apply is already in progress")
        self.job = {"state": "running", "message": "Checking settings and the installed game"}
        def worker():
            try:
                result = apply(payload, self.progress, self.root)
                self.job = {"state": "complete", "message": "Applied to game. Ready for your next launch.", "result": result}
            except Exception as error:
                self.job = {"state": "failed", "message": str(error)}
            finally: self.lock.release()
        threading.Thread(target=worker, daemon=False).start()
    def progress(self, message): self.job = {"state": "running", "message": message}

def handler(app, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def allowed(self):
            return self.headers.get("Host") == f"127.0.0.1:{port}"
        def respond(self, code, data, mime="application/json"):
            if not isinstance(data, bytes): data = json.dumps(data).encode()
            self.send_response(code); self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if not self.allowed(): return self.respond(403, {"error": "Local access only"})
            try:
                if self.path == "/api/config": return self.respond(200, app.settings())
                if self.path == "/api/status": return self.respond(200, app.job)
                if self.path == "/api/health": return self.respond(200, {"app": "mountain-relief", "root": str(app.root)})
                if self.path == "/apply.js":
                    return self.respond(200, (app.root / "source/standalone/relief_apply.js").read_bytes(), "text/javascript; charset=utf-8")
                if self.path in ("/", "/index.html"):
                    return self.respond(200, app.page, "text/html; charset=utf-8")
                if self.path in app.assets:
                    return self.respond(200, app.assets[self.path], "image/png")
                return self.respond(404, {"error": "Not found"})
            except Exception as error: return self.respond(500, {"error": str(error)})
        def do_POST(self):
            origin = self.headers.get("Origin")
            if not self.allowed() or origin != f"http://127.0.0.1:{port}" or self.headers.get("X-Relief-Token") != app.token:
                return self.respond(403, {"error": "Open the local relief page to apply changes"})
            if self.path != "/api/apply": return self.respond(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536: raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length))
                # Reject stale/invalid settings before starting a background job.
                from relief_apply import request_settings
                request_settings(payload, app.root)
                app.start(payload)
                self.respond(202, {"state": "running"})
            except (ValueError, AssertionError, KeyError, TypeError) as error:
                self.respond(400, {"error": str(error)})
    return Handler

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    app = App()
    try: server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app, args.port))
    except OSError:
        # Reuse only our own existing workspace service, never an unrelated port.
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=3) as response:
            data = json.load(response)
        if data != {"app": "mountain-relief", "root": str(ROOT)}: raise RuntimeError("Relief page port is occupied")
        if args.open: webbrowser.open(f"http://127.0.0.1:{args.port}/")
        return
    if args.open: webbrowser.open(f"http://127.0.0.1:{args.port}/")
    print(f"Mountain relief page: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()

if __name__ == "__main__": main()
