from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
from core import round_ops
from metrics.event_trace import EventTrace
from core.node import Node
from identity.observation import Observation
from identity.registry import IdentityParams, IdentityRegistry
from sampling import get_strategy


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, ConnectionError, OSError):
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


def _wait_config(base, poll=0.1, tries=600):
    for _ in range(tries):
        status, cfg = _get(f"{base}/config")
        if status == 200:
            return cfg
        time.sleep(poll)
    raise RuntimeError("controller unreachable")


def _block_get(url, poll=0.05):
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


def _tag(payload, job):
    if job is not None:
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


def run_honest(base, node_id, cfg, job=None):
    params, registry, scenario = _build(cfg)
    apath = f"{base}/assignment/{node_id}" if job is None else f"{base}/assignment/{job}/{node_id}"
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
        scenario.churn_reset({node_id: node}, r)
        _block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r, "peers": node.peers}, job))
        opath = f"{base}/offers/{node_id}/{r}" if job is None else f"{base}/offers/{job}/{node_id}/{r}"
        offers = _block_get(opath)["offers"]

        # 5.1.8: dogadjaji nastaju lokalno na cvoru, pa se salju controlleru u izvestaju
        trace = EventTrace() if cfg.get("trace_events") else None
        # ista admission logika koju koristi i in-process Engine
        offered, rejected, reasons = round_ops.admit(node, offers, strategy, r, trace=trace)

        own = node.estimate
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r, "value": scenario.broadcast_value(node_id, own, r)}, job))
        vals = _block_post(f"{base}/values", _tag(
            {"node_id": node_id, "round": r, "peers": node.peers}, job))["values"]

        # isti heartbeat/timeout mehanizam kao in-process
        responders, timeouts = round_ops.heartbeat(
            node, list(node.peers), scenario, r, None, timeout_rounds, trace=trace)
        received = [vals[str(p)] for p in responders if str(p) in vals]
        node.estimate = aggregation.aggregate(own, received)
        if trace is not None:
            trace.estimate(r, node_id, node.estimate)

        _block_post(f"{base}/report", _tag({
            "node_id": node_id, "round": r, "peers": node.peers, "estimate": node.estimate,
            "offered": offered, "rejected": rejected, "data_msgs": len(received),
            "rej_invalid_pow": reasons["invalid_pow"], "rej_too_young": reasons["too_young"],
            "rej_low_score": reasons["low_score"], "rej_bucket_full": reasons["bucket_full"],
            "timeouts": timeouts,
            "trace": trace.csv_rows() if trace is not None else None}, job))


def run_malicious(base, node_id, cfg, job=None):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        _block_post(f"{base}/broadcast", _tag(
            {"node_id": node_id, "round": r, "value": scenario.broadcast_value(node_id, 0.0, r)}, job))


def run_node(base, node_id):
    cfg = _wait_config(base)
    if node_id in set(cfg["byzantine"]) | set(cfg["sybil"]):
        run_malicious(base, node_id, cfg)
    else:
        run_honest(base, node_id, cfg)


def run_matrix_node(base, node_id):
    info = _block_get(f"{base}/jobs")
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
    if os.environ.get("MODE") == "matrix":
        run_matrix_node(base, node_id)
    else:
        run_node(base, node_id)
    print(f"node {node_id} done", flush=True)


if __name__ == "__main__":
    main()