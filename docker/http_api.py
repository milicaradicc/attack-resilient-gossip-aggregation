from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The HTTP layer: the only point at which the controller touches the network.
# The handler holds no experiment logic - it only translates requests into calls
# on the matrix state, and answers 425 while a barrier condition is not met.
#
# 5.1.5: aggregation values do NOT pass through here. Every participant runs its
# own value server (docker/value_server.py) and neighbours fetch from each other
# directly. What the controller still provides is:
#
#   - the job description and the initial assignment
#   - the peer sampling service (POST /peers, GET /offers), which needs a
#     barrier because the candidate offer is built for all nodes at once
#   - the address directory (POST /address, GET /addresses), the equivalent of
#     a bootstrap node or DNS: it tells a node where its neighbours live, not
#     what they are saying
#   - metric collection (POST /report)


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
                # the directory is complete only once every participant has
                # registered; until then a node cannot reach all its neighbours
                addresses = matrix.all_addresses()
                self._send(200 if addresses is not None else 425,
                           {"addresses": addresses} if addresses is not None
                           else {"ready": False})
            elif parts[0] == "finished":
                # a participant must keep its value server up until every job is
                # done: a slower neighbour may still be collecting an earlier
                # round from it
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