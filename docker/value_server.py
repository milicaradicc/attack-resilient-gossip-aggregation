from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ValueStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._published = {} # (job, round) -> {"value": float|None, "responds": bool}

    def publish(self, job: int, round_now: int, value, responds: bool) -> None:
        with self._lock:
            self._published[(job, round_now)] = {"value": value, "responds": responds}

    def get(self, job: int, round_now: int):
        with self._lock:
            return self._published.get((job, round_now))


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


def make_handler(store: ValueStore, node_id: int):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = self.path.strip("/").split("/")
            if parts[0] != "value" or len(parts) != 3:
                self._send(404, {})
                return
            job, round_now = int(parts[1]), int(parts[2])
            entry = store.get(job, round_now)
            if entry is None:
                self._send(425, {"ready": False})
            elif not entry["responds"]:
                self._send(503, {})
            else:
                self._send(200, {"node_id": node_id, "value": entry["value"]})

    return Handler


def serve(store: ValueStore, node_id: int, host: str = "0.0.0.0", port: int = 0):
    return _Server((host, port), make_handler(store, node_id))