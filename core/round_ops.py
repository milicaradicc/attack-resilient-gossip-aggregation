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
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=round_now, last_seen_round=round_now,
            successful_exchanges=1 if exchanged else 0, nonce=nonce)
    else:
        obs.last_seen_round = round_now
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0


def send_peer_request(node, round_now: int, transport=None) -> None:
    if transport is None:
        return
    transport.request_peers(round_now, node.node_id, None)


def receive_offers(node, offers, round_now: int, transport=None) -> None:
    if transport is None:
        return
    for offer in offers:
        candidate, nonce = offer if isinstance(offer, (tuple, list)) else (offer, None)
        transport.offer(round_now, candidate, node.node_id, nonce=nonce)


def admit(node, sampling, round_now: int, offered: List = None,
          trace=None, transport=None) -> Tuple[int, int, Dict[str, int]]:
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
    considered = 0
    for candidate, nonce in exchanges:
        observe(node, candidate, round_now, exchanged=False, nonce=nonce)
        if candidate == node.node_id or candidate in node.peers:
            continue
        considered += 1
        if sampling.accept_peer(node, candidate, round_now):
            victim = sampling.evict_peer(node, round_now, candidate)
            if victim is not None:
                node.peers.remove(victim)
                if trace is not None:
                    trace.evict(round_now, node.node_id, victim, "replaced_by", candidate)
            node.peers.append(candidate)
            if transport is not None:
                transport.accept(round_now, node.node_id, candidate)
            if trace is not None:
                trace.accept(round_now, node.node_id, candidate)
        else:
            why = sampling.reason(node, candidate, round_now) or "self_or_duplicate"
            reasons[why] = reasons.get(why, 0) + 1
            if transport is not None:
                transport.reject(round_now, node.node_id, candidate, why)
            if trace is not None:
                trace.reject(round_now, node.node_id, candidate, why)
    return considered, sum(reasons.values()), reasons


def heartbeat(node, peers: List[int], round_now: int, timeout_rounds: int,
              responds, trace=None, transport=None) -> Tuple[List[int], int]:
    responders = []
    for p in peers:
        if transport is not None:
            transport.probe(round_now, node.node_id, p)
        if responds(p):
            observe(node, p, round_now, exchanged=True)
            responders.append(p)
        else:
            obs = node.observations.get(p)
            if obs is not None:
                obs.missed_heartbeats += 1
                obs.missed_total += 1
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
    out = {}
    for hid, node in nodes.items():
        out[hid] = scenario.broadcast_value(hid, node.estimate, round_now)
    for m in sorted(scenario.malicious_ids): # fixed order, for determinism
        value = scenario.broadcast_value(m, 0.0, round_now)
        if value is NO_MESSAGE:
            continue
        out[m] = value
        if trace is not None and scenario.active(round_now):
            trace.malicious_broadcast(round_now, m, value,
                                      scenario.params.byzantine_profile)
    return out


def deliver(node, responders: List[int], emitted: Dict[int, float],
            round_now: int, transport=None, scenario=None) -> List[int]:
    senders = [p for p in responders if p in emitted]
    if scenario is not None:
        senders = [p for p in senders
                   if scenario.sends_value_to(p, node.node_id, round_now)]
    if transport is not None:
        for p in senders:
            transport.send_value(round_now, p, node.node_id, emitted[p])
    return senders