from __future__ import annotations

import json
import os
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
from identity.observation import Observation
from identity.registry import IdentityParams, IdentityRegistry
from sampling import get_strategy


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read()) # statusni kod i telo
    except urllib.error.HTTPError as e: # server odgovorio sa kodom greske
        return e.code, None
    except (urllib.error.URLError, ConnectionError, OSError): # server nije odgovorio
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
    # ponavlja se zahtev dok se ne dobije 200, pedeset milisek da se ne zagusi 
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


def _sendable(value):
    # zadrzana poruka (delay) salje se kao None, da barijera i dalje broji ovog
    # ucesnika, a controller je ne isporucuje susedima
    return None if value is NO_MESSAGE else value


def _tag(payload, job):
    # svaki zahtev nosi oznaku konfiguracije, da se stanja razlicitih poslova
    # iz matrice ne bi mesala na controlleru
    payload["job"] = job
    return payload


def _build(cfg):
    ip = cfg["id_params"]
    params = IdentityParams(**ip)
    registry = IdentityRegistry()
    for k, v in cfg["registry"].items():
        registry.register(int(k), v)
    scenario = Scenario(set(cfg["honest"]), set(cfg["byzantine"]), set(cfg["sybil"]),
                        AttackParams(**cfg["attack"]))
    return params, registry, scenario


def run_honest(base, node_id, cfg, job):
    params, registry, scenario = _build(cfg)
    if node_id == 1 or node_id == "1":
        print(cfg)
        print("///////////////////////////////////////////////////////////")
        print(params,registry,scenario)
    apath = f"{base}/assignment/{job}/{node_id}"
    _, assign = _get(apath)
    node = Node.create(node_id, assign["x_local"])
    node.peers = list(assign["peers"])
    for p in node.peers:
        node.observations[p] = Observation(first_seen_round=0, last_seen_round=0)

    agg_kwargs = {"alpha": cfg["trim_alpha"]} if cfg["aggregation"] == "trimmed_mean" else {}
    aggregation = get_aggregation(cfg["aggregation"], **agg_kwargs)
    strategy = get_strategy(cfg["strategy"], cfg["peer_set_size"], registry, params)
    timeout_rounds = cfg["timeout_rounds"]

    for r in range(1, cfg["num_rounds"] + 1):
        scenario.before_round({node_id: node}, r)
        _block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r, "peers": node.peers}, job))
        opath = f"{base}/offers/{job}/{node_id}/{r}"
        offers = _block_get(opath)["offers"]

        # 5.1.8: dogadjaji nastaju lokalno na cvoru, pa se salju controlleru u izvestaju
        trace = EventTrace() if cfg.get("trace_events") else None
        # 5.1.5: poruke se broje po klasi, isto kao u in-process putanji
        # 5.1.5: isti transportni sloj koji koristi i in-process putanja
        transport = Transport()
        # ista admission logika koju koristi i in-process Engine
        # discovery kao razmena: zahtev pa ponude, koje admit preuzima iz sanduceta
        round_ops.request_peers(node, offers, r, transport=transport)
        offered, rejected, reasons = round_ops.admit(node, strategy, r,
                                                     trace=trace, transport=transport)

        own = node.estimate
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r,
             "value": _sendable(scenario.broadcast_value(node_id, own, r))}, job))
        vals = _block_post(f"{base}/values", _tag(
            {"node_id": node_id, "round": r, "peers": node.peers}, job))["values"]

        # isti heartbeat/timeout mehanizam kao in-process
        responders, timeouts = round_ops.heartbeat(
            node, list(node.peers), scenario, r, None, timeout_rounds, trace=trace,
            transport=transport)
        # svaki sused salje svoju vrednost kao zasebnu poruku ovom cvoru,
        # istom funkcijom koju koristi i in-process putanja
        emitted = {int(k): v for k, v in vals.items()}
        round_ops.deliver(node, responders, emitted, r, transport=transport)
        incoming = transport.receive(node_id, messages.AGGREGATE)
        received = [m.payload for m in incoming]
        node.estimate = aggregation.aggregate(own, received)
        if trace is not None:
            trace.estimate(r, node_id, node.estimate)

        _block_post(f"{base}/report", _tag({
            "node_id": node_id, "round": r, "peers": node.peers, "estimate": node.estimate,
            "offered": offered, "rejected": rejected, "data_msgs": transport.data,
            "control_msgs": transport.control,
            "rej_invalid_pow": reasons["invalid_pow"], "rej_too_young": reasons["too_young"],
            "rej_low_score": reasons["low_score"], "rej_bucket_full": reasons["bucket_full"],
            "timeouts": timeouts,
            "trace": trace.csv_rows() if trace is not None else None}, job))


def run_malicious(base, node_id, cfg, job):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r,
             "value": _sendable(scenario.broadcast_value(node_id, 0.0, r))}, job))


def run_matrix_node(base, node_id):
    info = _block_get(f"{base}/jobs") # {"n_jobs": 36, "max_nodes": 14}
    print(info)
    for job in range(info["n_jobs"]):
        cfg = _block_get(f"{base}/job/{job}")
        if node_id >= cfg["participants"]:
            continue
        if node_id in set(cfg["byzantine"]) | set(cfg["sybil"]):
            run_malicious(base, node_id, cfg, job)
        else:
            run_honest(base, node_id, cfg, job)


def main():
    base = os.environ["CONTROLLER_URL"]
    node_id = int(os.environ["NODE_ID"])
    run_matrix_node(base, node_id)
    print(f"node {node_id} done", flush=True)


if __name__ == "__main__":
    main()