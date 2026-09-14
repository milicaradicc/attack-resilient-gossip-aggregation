from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


def make_handler(matrix):
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

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            parts = self.path.strip("/").split("/")
            if parts[0] == "jobs":
                self._send(200, {"n_jobs": len(matrix.specs), "max_nodes": matrix.max_nodes})
            elif parts[0] == "job":
                self._send(200, matrix.job_payload(int(parts[1])))
            elif parts[0] == "assignment":
                job, i = int(parts[1]), int(parts[2])
                st = matrix.state_for(job)
                self._send(200, {"node_id": i, **st.assignments[i]})
            elif parts[0] == "addresses":
                addresses = matrix.all_addresses()
                self._send(200 if addresses is not None else 425,
                           {"addresses": addresses} if addresses is not None
                           else {"ready": False})
            elif parts[0] == "finished":
                done = matrix.done()
                self._send(200 if done else 425, {"done": done})
            elif parts[0] == "offers":
                job, i, r = int(parts[1]), int(parts[2]), int(parts[3])
                st = matrix.state_for(job)
                with st.lock:
                    st.maybe_build_offers(r)
                    ready = (r, i) in st.offers
                    offers = st.offers.get((r, i))
                self._send(200 if ready else 425,
                           {"offers": offers} if ready else {"ready": False})
            else:
                self._send(404, {})

        def do_POST(self):
            parts = self.path.strip("/").split("/")
            data = self._body()
            if parts[0] == "address":
                matrix.register_address(data["node_id"], data["url"])
                self._send(200, {"ok": True})
                return
            job = data.get("job", 0)
            st = matrix.state_for(job)
            if parts[0] == "peers":
                with st.lock:
                    st.peers_in.setdefault(data["round"], {})[data["node_id"]] = data["peers"]
                self._send(200, {"ok": True})
            elif parts[0] == "report":
                with st.lock:
                    st.reports.setdefault(data["round"], {})[data["node_id"]] = data
                    st.maybe_record(data["round"])
                    finished = st.complete()
                if finished:
                    matrix.finalize(job)
                self._send(200, {"ok": True})
            else:
                self._send(404, {})

    return Handler


def serve(matrix, host: str, port: int):
    return _Server((host, port), make_handler(matrix))