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
    # ako peer nije vidjen ranije dodaj observation; nonce je ono sto je peer
    # sam predstavio u ponudi (videti request_peers/transport.offer) — ostaje
    # zapamcen uz njega, ne trazi se ponovo iz nekog registra
    if obs is None:
        node.observations[other] = Observation(
            first_seen_round=round_now, last_seen_round=round_now,
            successful_exchanges=1 if exchanged else 0, nonce=nonce)
    # ako jeste ziv je i osvezava se
    else:
        obs.last_seen_round = round_now
        if exchanged:
            obs.successful_exchanges += 1
            obs.missed_heartbeats = 0


def request_peers(node, candidates: List[int], round_now: int,
                  transport=None, nonces: Dict[int, int] = None) -> None:
    # 5.1.5: discovery kao razmena — cvor salje zahtev, a odgovor stize kao niz
    # peer_exchange poruka, po jedna za svakog ponudjenog kandidata. Izvor svake
    # ponude je sam identitet koji se reklamira, a poruka nosi i njegov PoW
    # nonce — 'nonces' ovde nije registar kome se admission obraca, nego samo
    # nacin da se u simulaciji sastavi ta poruka (honest cvor bi nonce citao
    # sam iz sebe; ovde ga za sve identitete drzi Engine/World jednom, o
    # nonce se pri admisiji nikad ne pita — samo se cita ono sto stigne u poruci)
    if transport is None:
        return
    transport.request_peers(round_now, node.node_id, node.node_id)
    nonces = nonces or {}
    for candidate in candidates:
        transport.offer(round_now, candidate, node.node_id, nonce=nonces.get(candidate))


def admit(node, sampling, round_now: int, offered: List = None,
          trace=None, transport=None) -> Tuple[int, int, Dict[str, int]]:
    # admission + eviction za JEDAN cvor. Kandidati (id, nonce) parovi se
    # preuzimaju iz sanduceta, gde su stigli kao odgovor na zahtev (videti
    # request_peers) — nonce je deo same poruke, ne trazi se nigde spolja.
    # Lista 'offered' koristi se samo kada transport nije zadat (npr. u
    # testovima) i moze biti gola lista id-jeva (bez PoW-a) ili (id, nonce) parova.
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
        # zabelezi u dnevnik (vidjanje, ne razmena) -> time mu starost pocinje da tece
        observe(node, candidate, round_now, exchanged=False, nonce=nonce)
        # ako je kandidat vec komsija skip
        if candidate in node.peers:
            continue
        # admission !!!!!!!!!!!! -> proverava PoW/starost/skor/bucket
        if sampling.accept_peer(node, candidate, round_now):
            # strategija odlucuje koga (i da li) izbaciti:
            # eclipse vraca najslabijeg iz istog bucketa kad je bucket pun,
            # ostale strategije globalno najslabijeg tek kad je ceo peer set pun
            victim = sampling.evict_peer(node, round_now, candidate)
            if victim is not None:
                node.peers.remove(victim)
                if transport is not None:
                    transport.evict(round_now, node.node_id, victim, "replaced_by")
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
            # povecaj brojace
            why = sampling.reason(node, candidate, round_now) or "self_or_duplicate"
            reasons[why] = reasons.get(why, 0) + 1
            if transport is not None:
                transport.reject(round_now, node.node_id, candidate, why)
            if trace is not None:
                trace.reject(round_now, node.node_id, candidate, why)
    return len(exchanges), sum(reasons.values()), reasons


def heartbeat(node, peers: List[int], scenario, round_now: int, rng,
              timeout_rounds: int, trace=None, transport=None) -> Tuple[List[int], int]:
    # ko odgovara ostaje u razmeni, ko cuti skuplja propustene otkucaje
    responders = []
    for p in peers:
        if transport is not None:
            transport.probe(round_now, node.node_id, p)
        if scenario.responds(p, round_now, rng):
            observe(node, p, round_now, exchanged=True)
            responders.append(p)
        else:
            obs = node.observations.get(p)
            if obs is not None:
                obs.missed_heartbeats += 1
                obs.missed_total += 1
    # timeout eviction: peer koji predugo cuti se izbacuje iz peer set-a
    timeouts = 0
    if timeout_rounds > 0:
        for p in list(node.peers):
            obs = node.observations.get(p)
            if obs is not None and obs.missed_heartbeats > timeout_rounds:
                node.peers.remove(p)
                obs.timeout_count += 1
                timeouts += 1
                if transport is not None:
                    transport.evict(round_now, node.node_id, p, "timeout")
                if trace is not None:
                    trace.evict(round_now, node.node_id, p, "timeout", None)
                if p in responders:
                    responders.remove(p)
    return responders, timeouts


def emitted_values(nodes: Dict[int, object], scenario, round_now: int,
                   trace=None) -> Dict[int, float]:
    # 5.1.4: vrednosti svih ucesnika zamrzavaju se na pocetku runde (tick barrier),
    # pa se tek onda isporucuju. Time isporuka ne zavisi od redosleda obrade cvorova.
    out = {}
    for hid, node in nodes.items():
        out[hid] = scenario.broadcast_value(hid, node.estimate, round_now)
    for m in sorted(scenario.malicious_ids): # fiksan redosled radi determinizma
        # placeholder 0.0 se ne koristi — napadac vraca vrednost po svom profilu
        value = scenario.broadcast_value(m, 0.0, round_now)
        if value is NO_MESSAGE:
            # poruka je zadrzana (delay); ovaj ucesnik u ovoj rundi ne salje nista
            continue
        out[m] = value
        if trace is not None and scenario.active(round_now):
            trace.malicious_broadcast(round_now, m, value,
                                      scenario.params.byzantine_profile)
    return out


def deliver(node, responders: List[int], emitted: Dict[int, float],
            round_now: int, transport=None) -> List[int]:
    # 5.1.5: svaki sused koji je odgovorio salje svoju vrednost kao zasebnu
    # data poruku ovom cvoru. Lazni identiteti (flooding) nemaju emitovanu
    # vrednost, pa ne salju nista.
    senders = [p for p in responders if p in emitted]
    if transport is not None:
        for p in senders:
            transport.send_value(round_now, p, node.node_id, emitted[p])
    return senders