from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
from attacks.base import NO_MESSAGE
from core import messages, round_ops
from core.transport import Transport
from metrics.event_trace import EventTrace
from core.node import Node
from docker import value_server
from identity.observation import Observation
from identity.params import IdentityParams
from sampling import get_strategy


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read()) # status code and body
    except urllib.error.HTTPError as e: # the server answered with an error code
        return e.code, None
    except (urllib.error.URLError, ConnectionError, OSError): # the server did not answer
        return 503, None


def _post(url, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, ConnectionError, OSError):
        return 503, None


def _block_get(url, poll=0.05):
    # the request is repeated until a 200 comes back; fifty milliseconds so the
    # other side does not get flooded
    while True:
        status, body = _get(url)
        if status == 200:
            return body
        time.sleep(poll)


def _block_post(url, obj, poll=0.05):
    while True:
        status, body = _post(url, obj)
        if status == 200:
            return body
        time.sleep(poll)


def _fetch_value(addresses, peer: int, job: int, round_now: int,
                 participants: int, poll=0.05):
    if peer >= participants:
        return None
    url = addresses.get(str(peer))
    if url is None:
        return None
    while True:
        status, body = _get(f"{url}/value/{job}/{round_now}")
        if status == 200:
            return body
        if status != 425:
            return None
        time.sleep(poll)


def _sendable(value):
    return None if value is NO_MESSAGE else value


def _tag(payload, job):
    payload["job"] = job
    return payload


def _build(cfg):
    ip = cfg["id_params"]
    params = IdentityParams(**ip)
    nonces = {int(k): v for k, v in cfg["nonces"].items()}
    scenario = Scenario(set(cfg["honest"]), set(cfg["byzantine"]), set(cfg["sybil"]),
                        AttackParams(**cfg["attack"]))
    return params, nonces, scenario


def run_honest(base, node_id, cfg, job, store, addresses):
    params, nonces, scenario = _build(cfg)
    apath = f"{base}/assignment/{job}/{node_id}"
    _, assign = _get(apath)
    node = Node.create(node_id, assign["x_local"])
    node.peers = list(assign["peers"])
    node.nonce = nonces.get(node_id, 0)
    for p in node.peers:
        node.observations[p] = Observation(first_seen_round=0, last_seen_round=0,
                                           nonce=nonces.get(p))

    agg_kwargs = {"alpha": cfg["trim_alpha"]} if cfg["aggregation"] == "trimmed_mean" else {}
    aggregation = get_aggregation(cfg["aggregation"], **agg_kwargs)
    strategy = get_strategy(cfg["strategy"], cfg["peer_set_size"], params, cfg.get("seed", 0))
    timeout_rounds = cfg["timeout_rounds"]
    participants = cfg["participants"]

    for r in range(1, cfg["num_rounds"] + 1):
        trace = EventTrace() if cfg.get("trace_events") else None
        transport = Transport()
        scenario.before_round({node_id: node}, r, trace=trace)

        own = node.estimate
        store.publish(job, r, _sendable(scenario.broadcast_value(node_id, own, r)),
                      responds=scenario.responds(node_id, r, None))

        responders, timeouts = round_ops.heartbeat(
            node, list(node.peers), r, timeout_rounds,
            lambda p: scenario.responds(p, r, None),
            trace=trace, transport=transport)

        values = {}
        for p in list(responders):
            reply = _fetch_value(addresses, p, job, r, participants)
            if reply is not None and reply["value"] is not None:
                values[p] = reply["value"]

        round_ops.deliver(node, responders, values, r, transport=transport)
        incoming = transport.receive(node_id, messages.AGGREGATE)
        received = [m.payload for m in incoming]

        node.estimate = aggregation.aggregate(own, received)
        if trace is not None:
            trace.estimate(r, node_id, node.estimate)

        round_ops.send_peer_request(node, r, transport=transport)
        _block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r, "peers": node.peers}, job))
        opath = f"{base}/offers/{job}/{node_id}/{r}"
        offers = _block_get(opath)["offers"]
        round_ops.receive_offers(node, offers, r, transport=transport)
        offered, rejected, reasons = round_ops.admit(node, strategy, r,
                                                     trace=trace, transport=transport)

        _block_post(f"{base}/report", _tag({
            "node_id": node_id, "round": r, "peers": node.peers, "estimate": node.estimate,
            "offered": offered, "rejected": rejected, "data_msgs": transport.data,
            "control_msgs": transport.control,
            "rej_invalid_pow": reasons["invalid_pow"], "rej_too_young": reasons["too_young"],
            "rej_low_score": reasons["low_score"], "rej_bucket_full": reasons["bucket_full"],
            "timeouts": timeouts,
            "trace": trace.csv_rows() if trace is not None else None}, job))


def run_malicious(base, node_id, cfg, job, store, addresses):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        store.publish(job, r,
                      _sendable(scenario.broadcast_value(node_id, 0.0, r)),
                      responds=scenario.responds(node_id, r, None))


def run_matrix_node(base, node_id, advertise_host="127.0.0.1", port=0):
    store = value_server.ValueStore()
    server = value_server.serve(store, node_id, port=port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://{advertise_host}:{server.server_address[1]}"
    _block_post(f"{base}/address", {"node_id": node_id, "url": url})
    addresses = _block_get(f"{base}/addresses")["addresses"]

    try:
        info = _block_get(f"{base}/jobs") # {"n_jobs": 36, "max_nodes": 14}
        for job in range(info["n_jobs"]):
            cfg = _block_get(f"{base}/job/{job}")
            if node_id >= cfg["participants"]:
                continue
            if node_id in set(cfg["byzantine"]) | set(cfg["sybil"]):
                run_malicious(base, node_id, cfg, job, store, addresses)
            else:
                run_honest(base, node_id, cfg, job, store, addresses)
    finally:
        _block_get(f"{base}/finished")
        server.shutdown()


def main():
    base = os.environ["CONTROLLER_URL"]
    node_id = int(os.environ["NODE_ID"])
    host = os.environ.get("NODE_HOST", f"node{node_id}")
    port = int(os.environ.get("NODE_PORT", "8100"))
    run_matrix_node(base, node_id, advertise_host=host, port=port)
    print(f"node {node_id} done", flush=True)


if __name__ == "__main__":
    main()