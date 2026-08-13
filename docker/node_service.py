from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from aggregation import get_aggregation
from attacks.scenario import AttackParams, Scenario
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


def _build(cfg):
    ip = cfg["id_params"]
    params = IdentityParams(**ip)
    registry = IdentityRegistry()
    for k, v in cfg["registry"].items():
        registry.register(int(k), v)
    scenario = Scenario(set(cfg["honest"]), set(cfg["byzantine"]), set(cfg["sybil"]),
                        AttackParams(**cfg["attack"]))
    return params, registry, scenario

# TODO rekaforisati isto kao u engine-u je
def _observe(node, other, r, exchanged):
    obs = node.observations.get(other)
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=r, last_seen_round=r,
            successful_exchanges=1 if exchanged else 0)
    else:
        obs.last_seen_round = r
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0


def run_honest(base, node_id, cfg):
    params, registry, scenario = _build(cfg)
    _, assign = _get(f"{base}/assignment/{node_id}")
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
        _block_post(f"{base}/peers", {"node_id": node_id, "round": r, "peers": node.peers})
        offers = _block_get(f"{base}/offers/{node_id}/{r}")["offers"]

        reasons = {"invalid_pow": 0, "too_young": 0, "low_score": 0,
                   "bucket_full": 0, "self_or_duplicate": 0}
        for c in offers:
            _observe(node, c, r, exchanged=False)
            if c in node.peers:
                continue
            if strategy.accept_peer(node, c, r):
                if len(node.peers) >= strategy.max_peers:
                    victim = strategy.evict_peer(node, r)
                    if victim is None:
                        continue
                    node.peers.remove(victim)
                node.peers.append(c)
            else:
                why = strategy.reason(node, c, r) or "self_or_duplicate"
                reasons[why] += 1
        offered = len(offers)
        rejected = sum(reasons.values())

        own = node.estimate
        _block_post(f"{base}/broadcast",
                    {"node_id": node_id, "round": r, "value": scenario.broadcast_value(node_id, own, r)})
        vals = _block_post(f"{base}/values",
                           {"node_id": node_id, "round": r, "peers": node.peers})["values"]

        responders = []
        for p in node.peers:
            if scenario.responds(p, r, None):
                _observe(node, p, r, exchanged=True)
                responders.append(p)
            else:
                obs = node.observations.get(p)
                if obs is not None:
                    obs.missed_heartbeats += 1
        timeouts = 0
        if timeout_rounds > 0:
            for p in list(node.peers):
                obs = node.observations.get(p)
                if obs is not None and obs.missed_heartbeats > timeout_rounds:
                    node.peers.remove(p)
                    timeouts += 1
                    if p in responders:
                        responders.remove(p)
        received = [vals[str(p)] for p in responders if str(p) in vals]
        node.estimate = aggregation.aggregate(own, received)

        _block_post(f"{base}/report", {
            "node_id": node_id, "round": r, "peers": node.peers, "estimate": node.estimate,
            "offered": offered, "rejected": rejected, "data_msgs": len(received),
            "rej_invalid_pow": reasons["invalid_pow"], "rej_too_young": reasons["too_young"],
            "rej_low_score": reasons["low_score"], "rej_bucket_full": reasons["bucket_full"],
            "timeouts": timeouts})


def run_malicious(base, node_id, cfg):
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        _block_post(f"{base}/broadcast",
                    {"node_id": node_id, "round": r, "value": scenario.broadcast_value(node_id, 0.0, r)})


def run_node(base, node_id):
    cfg = _wait_config(base)
    if node_id in set(cfg["byzantine"]) | set(cfg["sybil"]):
        run_malicious(base, node_id, cfg)
    else:
        run_honest(base, node_id, cfg)


def main():
    base = os.environ["CONTROLLER_URL"]
    node_id = int(os.environ["NODE_ID"])
    run_node(base, node_id)
    print(f"node {node_id} done", flush=True)


if __name__ == "__main__":
    main()
