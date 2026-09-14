from __future__ import annotations

from typing import Dict, List, Tuple

from attacks.base import FLOOD_BASE, NO_MESSAGE
from core import messages
from identity.observation import Observation


REASON_KEYS = ("invalid_pow", "too_young", "low_score", "bucket_full", "self_or_duplicate")


def empty_reasons() -> Dict[str, int]:
    return {k: 0 for k in REASON_KEYS}


def observe(node, other: int, round_now: int, exchanged: bool, nonce: int = None) -> None:
    obs = node.observations.get(other)
    # if the peer has not been seen before, add an observation; the nonce is what
    # the peer itself presented in its offer (see receive_offers/transport.offer)
    # and stays remembered with it, never looked up again from any registry
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=round_now, last_seen_round=round_now,
            successful_exchanges=1 if exchanged else 0, nonce=nonce)
    # otherwise it is alive, so refresh it
    else:
        obs.last_seen_round = round_now
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0


def send_peer_request(node, round_now: int, transport=None) -> None:
    # 5.1.5, first half of discovery: the node SENDS the request and at that point
    # knows nothing more. Who the candidates are is decided outside of it, and the
    # answer only arrives in the second half (receive_offers), as messages.
    #
    # The request has no destination among the nodes: it is addressed to the peer
    # sampling service (the controller in the distributed path, the Engine in the
    # in-process one), which is not a participant in the aggregation. Transport
    # counts such a message but has nobody to deliver it to - see Transport.send.
    if transport is None:
        return
    transport.request_peers(round_now, node.node_id, None)


def receive_offers(node, offers, round_now: int, transport=None) -> None:
    # 5.1.5, second half: the offers ARRIVE. Each one is a separate peer_exchange
    # message whose source is the identity advertising itself, carrying that
    # identity's PoW nonce as its payload. From here on the node knows only what
    # landed in its mailbox - no registry of identities or nonces is consulted.
    #
    # 'offers' is what came off the wire: a list of (identity, nonce) pairs. A bare
    # id is accepted as well, for tests that do not model PoW.
    if transport is None:
        return
    for offer in offers:
        candidate, nonce = offer if isinstance(offer, (tuple, list)) else (offer, None)
        transport.offer(round_now, candidate, node.node_id, nonce=nonce)


def admit(node, sampling, round_now: int, offered: List = None,
          trace=None, transport=None) -> Tuple[int, int, Dict[str, int]]:
    # admission + eviction for ONE node. The candidates, as (id, nonce) pairs, are
    # taken out of the mailbox where they arrived as the answer to the request
    # (see receive_offers) - the nonce is part of the message itself and is never
    # looked up anywhere else. The 'offered' list is used only when no transport is
    # given (e.g. in tests) and may be a bare list of ids (no PoW) or (id, nonce) pairs.
    if transport is not None:
        exchanges = [(m.source, m.payload) for m in transport.receive(
            node.node_id, messages.PEER_EXCHANGE)]
    elif offered is None:
        exchanges = []
    else:
        exchanges = [o if isinstance(o, tuple) else (o, None) for o in offered]
    reasons = empty_reasons()
    if trace is not None:
        flooded = sum(1 for c, _ in exchanges if c >= FLOOD_BASE)
        if flooded:
            trace.flooding(round_now, node.node_id, flooded)
    for candidate, nonce in exchanges:
        # record it in the log (a sighting, not an exchange) -> its age starts running
        observe(node, candidate, round_now, exchanged=False, nonce=nonce)
        # if the candidate is already a neighbour, skip
        if candidate in node.peers:
            continue
        # admission -> checks PoW / age / score / bucket
        if sampling.accept_peer(node, candidate, round_now):
            # the strategy decides who (if anyone) to evict:
            # eclipse returns the weakest from the same bucket once that bucket is full,
            # the other strategies the globally weakest only once the whole peer set is full
            victim = sampling.evict_peer(node, round_now, candidate)
            if victim is not None:
                # eviction sends no message: it is a local decision (see core/transport.py)
                node.peers.remove(victim)
                if trace is not None:
                    trace.evict(round_now, node.node_id, victim, "replaced_by", candidate)
            elif len(node.peers) >= sampling.max_peers:
                if trace is not None:
                    trace.reject(round_now, node.node_id, candidate, "peer_set_full")
                continue
            node.peers.append(candidate)
            if transport is not None:
                transport.accept(round_now, node.node_id, candidate)
            if trace is not None:
                trace.accept(round_now, node.node_id, candidate)
        else:
            # bump the counters
            why = sampling.reason(node, candidate, round_now) or "self_or_duplicate"
            reasons[why] = reasons.get(why, 0) + 1
            if transport is not None:
                transport.reject(round_now, node.node_id, candidate, why)
            if trace is not None:
                trace.reject(round_now, node.node_id, candidate, why)
    return len(exchanges), sum(reasons.values()), reasons


def heartbeat(node, peers: List[int], scenario, round_now: int, rng,
              timeout_rounds: int, trace=None, transport=None,
              responds_fn=None) -> Tuple[List[int], int]:
    # whoever answers stays in the exchange; whoever stays silent accumulates
    # missed heartbeats
    #
    # 'responds_fn' says how "did this peer answer" is decided. In the in-process
    # path there is nobody to ask, so the scenario answers on the peer's behalf.
    # In the distributed path the node learns it from the peer itself: the answer
    # came back over the wire, or it did not (docker/node.py). Both must agree,
    # because the attacker container evaluates the very same scenario rule on its
    # own identity - the difference is only who evaluates it.
    answered = responds_fn if responds_fn is not None else (
        lambda peer: scenario.responds(peer, round_now, rng))
    responders = []
    for p in peers:
        if transport is not None:
            transport.probe(round_now, node.node_id, p)
        if answered(p):
            observe(node, p, round_now, exchanged=True)
            responders.append(p)
        else:
            obs = node.observations.get(p)
            if obs is not None:
                obs.missed_heartbeats += 1
                obs.missed_total += 1
    # timeout eviction: a peer that stays silent too long is dropped from the peer set
    timeouts = 0
    if timeout_rounds > 0:
        for p in list(node.peers):
            obs = node.observations.get(p)
            if obs is not None and obs.missed_heartbeats > timeout_rounds:
                node.peers.remove(p)
                obs.timeout_count += 1
                timeouts += 1
                if trace is not None:
                    trace.evict(round_now, node.node_id, p, "timeout", None)
                if p in responders:
                    responders.remove(p)
    return responders, timeouts


def emitted_values(nodes: Dict[int, object], scenario, round_now: int,
                   trace=None) -> Dict[int, float]:
    # 5.1.4: the values of all participants are frozen at the start of the round
    # (tick barrier) and only then delivered. Delivery therefore does not depend
    # on the order in which nodes are processed.
    out = {}
    for hid, node in nodes.items():
        out[hid] = scenario.broadcast_value(hid, node.estimate, round_now)
    for m in sorted(scenario.malicious_ids): # fixed order, for determinism
        # the 0.0 placeholder is not used - the attacker returns a value from its profile
        value = scenario.broadcast_value(m, 0.0, round_now)
        if value is NO_MESSAGE:
            # the message was held back (delay); this participant sends nothing this round
            continue
        out[m] = value
        if trace is not None and scenario.active(round_now):
            trace.malicious_broadcast(round_now, m, value,
                                      scenario.params.byzantine_profile)
    return out


def deliver(node, responders: List[int], emitted: Dict[int, float],
            round_now: int, transport=None) -> List[int]:
    # 5.1.5: every neighbour that answered sends its value to this node as a
    # separate data message. Fake identities (flooding) have no emitted value, so
    # they send nothing.
    senders = [p for p in responders if p in emitted]
    if transport is not None:
        for p in senders:
            transport.send_value(round_now, p, node.node_id, emitted[p])
    return senders