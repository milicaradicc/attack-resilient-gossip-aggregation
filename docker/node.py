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


def _fetch_peer(addresses, peer: int, job: int, round_now: int,
                participants: int, poll=0.05):
    # 5.1.5: the aggregation value is taken FROM THE NEIGHBOUR, not from the
    # controller. Returns the neighbour's answer, or None when it did not answer.
    #
    #   425 -> it has not reached this round yet, so wait and ask again. This is
    #          the tick barrier (5.1.4), now enforced between two peers instead
    #          of globally.
    #   503 -> it has reached the round and is not answering (churn, selective
    #          forwarding, an unresponsive profile). That is silence, not a wait.
    #   200 -> {"value": x} or {"value": null} when it deliberately sends nothing
    #          this round (delay).
    #
    # A flooding identity has no container at all, so there is nothing to ask -
    # and that is exactly what makes it cost the victim a wasted probe and,
    # eventually, a timeout.
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
    # a held-back message (delay) is published as None: the neighbour sees that
    # this participant reached the round and chose to send nothing
    return None if value is NO_MESSAGE else value


def _tag(payload, job):
    # every request carries the configuration tag, so the states of different jobs
    # from the matrix do not get mixed up on the controller
    payload["job"] = job
    return payload


def _build(cfg):
    ip = cfg["id_params"]
    params = IdentityParams(**ip)
    # nonces: every identity has solved its own PoW; here it is only unpacked from
    # what the job controller passed along as part of the job configuration
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
        # initial topology: a bootstrap peer, whose nonce is read directly from
        # what was assigned to it as its own nonce, not from a registry
        node.observations[p] = Observation(first_seen_round=0, last_seen_round=0,
                                           nonce=nonces.get(p))

    agg_kwargs = {"alpha": cfg["trim_alpha"]} if cfg["aggregation"] == "trimmed_mean" else {}
    aggregation = get_aggregation(cfg["aggregation"], **agg_kwargs)
    strategy = get_strategy(cfg["strategy"], cfg["peer_set_size"], params)
    timeout_rounds = cfg["timeout_rounds"]
    participants = cfg["participants"]

    for r in range(1, cfg["num_rounds"] + 1):
        # 5.1.8: events arise locally at the node, so they are sent to the
        # controller in the report. The log is created before before_round,
        # because a churn departure (3.8) changes the peer set before discovery
        # even starts and has to end up in the log.
        trace = EventTrace() if cfg.get("trace_events") else None
        scenario.before_round({node_id: node}, r, trace=trace)
        # 5.1.5: the same transport layer the in-process path uses; messages are
        # counted per class
        transport = Transport()

        # --- 1. gossip over the peer set the node already has ----------------
        # Aggregation comes first and overlay maintenance second. A node gossips
        # with the neighbours it currently holds, and only then does peer
        # sampling reshape the set for the NEXT round. The other way round,
        # admission would rewrite the peer set before the bootstrap topology was
        # ever used for a single exchange.
        #
        # 5.1.4: the value is frozen and published BEFORE anything is fetched, so
        # a neighbour asking for this round always gets the pre-update estimate
        # no matter who is running ahead. This is what makes the barrier work
        # without a central collector.
        own = node.estimate
        store.publish(job, r, _sendable(scenario.broadcast_value(node_id, own, r)),
                      responds=scenario.responds(node_id, r, None))

        answers = {}
        for p in list(node.peers):
            reply = _fetch_peer(addresses, p, job, r, participants)
            if reply is not None:
                answers[p] = reply["value"]

        # the same heartbeat/timeout mechanism as in-process, except that whether
        # a peer answered is no longer decided here - it is what came back (or
        # did not) from that peer's own server
        responders, timeouts = round_ops.heartbeat(
            node, list(node.peers), scenario, r, None, timeout_rounds, trace=trace,
            transport=transport, responds_fn=lambda p: p in answers)
        # every neighbour that answered with a value sends it to this node as a
        # separate message, through the same function the in-process path uses
        emitted = {p: v for p, v in answers.items() if v is not None}
        round_ops.deliver(node, responders, emitted, r, transport=transport)
        incoming = transport.receive(node_id, messages.AGGREGATE)
        received = [m.payload for m in incoming]
        node.estimate = aggregation.aggregate(own, received)
        if trace is not None:
            trace.estimate(r, node_id, node.estimate)

        # --- 2. overlay maintenance, for the next round -----------------------
        # discovery is a genuine request, then the answer. The node sends the
        # request and reports its current peer set, and only then does the answer
        # come back. It does not know its candidates before asking, and it does
        # not compute them itself - the peer sampling service (the controller)
        # decides, as it would in a real overlay.
        round_ops.send_peer_request(node, r, transport=transport)
        _block_post(f"{base}/peers", _tag({"node_id": node_id, "round": r, "peers": node.peers}, job))
        opath = f"{base}/offers/{job}/{node_id}/{r}"
        # what arrives is a list of (identity, nonce) pairs: every offer carries
        # the PoW of the identity advertising itself, so admission reads the nonce
        # straight out of the message instead of consulting a registry
        offers = _block_get(opath)["offers"]
        round_ops.receive_offers(node, offers, r, transport=transport)
        # the same admission logic the in-process Engine uses; it takes the
        # candidates out of the mailbox
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
    # The attacker now touches no controller endpoint at all: it publishes its
    # value on its own server and its neighbours come and take it. Silence
    # (churn, selective forwarding) is published as "not answering", so the
    # victim experiences it as a probe that went unanswered rather than as a
    # flag it read out of a shared model.
    _, _, scenario = _build(cfg)
    for r in range(1, cfg["num_rounds"] + 1):
        store.publish(job, r,
                      _sendable(scenario.broadcast_value(node_id, 0.0, r)),
                      responds=scenario.responds(node_id, r, None))


def run_matrix_node(base, node_id, advertise_host="127.0.0.1", port=0):
    # 5.1.5: the node first brings up its own value server and registers where it
    # can be reached. Only once every participant has registered does the
    # directory answer, so nobody starts fetching from a neighbour that is not
    # listening yet.
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
        # kept alive until the very end: a slower neighbour may still be
        # collecting an earlier round from this node, so the server only goes
        # down once the controller says every job is finished
        _block_get(f"{base}/finished")
        server.shutdown()


def main():
    base = os.environ["CONTROLLER_URL"]
    node_id = int(os.environ["NODE_ID"])
    # inside compose every node is reachable under its service name
    host = os.environ.get("NODE_HOST", f"node{node_id}")
    port = int(os.environ.get("NODE_PORT", "8100"))
    run_matrix_node(base, node_id, advertise_host=host, port=port)
    print(f"node {node_id} done", flush=True)


if __name__ == "__main__":
    main()