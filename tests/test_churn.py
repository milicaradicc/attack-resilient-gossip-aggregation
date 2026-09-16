from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from core.setup import build_world
from in_process.matrix import run_single


def _spec(**over):
    base = dict(n_honest=15, beta=0.3, overlay="sybil_resistant",
                aggregation="trimmed_mean", seed=1, num_rounds=40,
                activate_round=1, pow_difficulty_bits=8, churn_period=5)
    base.update(over)
    return spec_from(**base)


def _absent_by_round(world, rounds):
    attackers = sorted(world.byzantine | world.sybil)
    return {r: {i for i in attackers if not world.scenario.responds(i, r, None)}
            for r in rounds}


def test_departures_are_not_synchronised():
    world = build_world(_spec())
    absent = _absent_by_round(world, range(1, 26))
    non_empty = [s for s in absent.values() if s]
    assert non_empty, "churn se nikada ne aktivira"
    assert len(set(map(frozenset, non_empty))) > 1, (
        "the same group of attackers leaves every time - the phases do not differ")


def test_attackers_never_all_leave_at_once():
    # ako svi napadaci cute u isto vreme, to je koordinisani ispad; churn znaci
    # da u svakoj rundi nedostaje neko drugi
    world = build_world(_spec(churn_period=5))
    attackers = world.byzantine | world.sybil
    absent = _absent_by_round(world, range(1, 26))
    assert all(len(s) < len(attackers) for s in absent.values()), (
        "postoji runda u kojoj su svi napadaci odsutni")


def test_each_attacker_follows_its_own_cycle():
    # svojstvo ciklusa: tacno churn_offline odsustava u svakom prozoru duzine
    # churn_period, ma gde faza tog identiteta pala
    world = build_world(_spec(churn_period=5, churn_offline=1))
    for attacker in sorted(world.byzantine | world.sybil):
        absent_rounds = [r for r in range(1, 21)
                         if not world.scenario.responds(attacker, r, None)]
        for start in range(1, 16):
            window = [r for r in absent_rounds if start <= r < start + 5]
            assert len(window) == 1, f"identity {attacker}, window {start}: {window}"


def test_absent_attacker_is_in_nobodys_peer_set():
    # odlazak je stvaran: dok je odsutan, identitet nije ni u jednom peer set-u,
    # pa ne prima ni heartbeat ni vrednost
    world = build_world(_spec(churn_period=6, churn_offline=2))
    ctx = world.scenario.ctx
    churn = world.scenario._churn()
    # pocetna topologija ne sadrzi napadace, pa se prvo rucno ubacuju
    attackers = sorted(world.byzantine | world.sybil)
    for node in world.nodes.values():
        node.peers = list(node.peers) + attackers

    for r in range(1, 13):
        world.scenario.before_round(world.nodes, r)
        away = set(churn.offline_ids(ctx, r))
        assert away, f"round {r}: churn removes nobody"
        for node in world.nodes.values():
            left_over = away & set(node.peers)
            assert not left_over, f"round {r}, node {node.node_id}: still holds {left_over}"
        # vrati ih, da sledeca runda proveri da li su ponovo uklonjeni
        for node in world.nodes.values():
            node.peers = list(node.peers) + [a for a in attackers if a not in node.peers]


def test_absent_attacker_is_not_offered_in_discovery():
    # peer poisoning bezuslovno reklamira svaki napadacki identitet; filter u
    # Scenario.offer_candidates mora da izbaci one koji trenutno nisu u mrezi
    world = build_world(_spec(churn_period=6, churn_offline=2))
    ctx = world.scenario.ctx
    churn = world.scenario._churn()
    rng = random.Random(7)
    present_were_offered = False
    for r in range(1, 13):
        away = set(churn.offline_ids(ctx, r))
        for node in world.nodes.values():
            offer = set(world.scenario.offer_candidates(node, r, rng))
            assert not (offer & away), (
                f"round {r}, node {node.node_id}: absent identity offered {offer & away}")
            if offer & (world.byzantine | world.sybil):
                present_were_offered = True
    # kontrola: napadaci koji jesu prisutni moraju i dalje biti ponudjeni, inace
    # bi ovaj test prolazio bez sadrzaja
    assert present_were_offered, "no attacker is ever offered - the filter is too wide"


def test_return_puts_the_identity_back_into_the_network():
    # posle odsustva identitet ponovo moze biti ponudjen i primljen
    world = build_world(_spec(churn_period=5, churn_offline=2))
    ctx = world.scenario.ctx
    churn = world.scenario._churn()
    attacker = sorted(world.byzantine | world.sybil)[0]
    rng = random.Random(3)
    comeback = next(r for r in range(2, 15) if churn.returning(ctx, attacker, r))
    assert churn.offline(ctx, attacker, comeback - 1), "runda pre povratka nije odsustvo"
    assert not churn.offline(ctx, attacker, comeback)
    offers = set()
    for node in world.nodes.values():
        offers |= set(world.scenario.offer_candidates(node, comeback, rng))
    assert attacker in offers, "po povratku identitet se nikome ne nudi"


def test_departure_is_written_to_the_trace():
    # 5.1.8: odlazak menja peer set, pa mora da ostavi trag. Bez toga bi se u
    # zapisu video drugi 'accept' istog identiteta bez 'evict' izmedju — stanje
    # koje se iz zapisa ne moze rekonstruisati.
    from metrics.event_trace import EventTrace
    trace = EventTrace()
    spec = _spec(n_honest=8, overlay="random", aggregation="mean",
                 num_rounds=12, churn_period=4, churn_offline=2,
                 timeout_rounds=3, trace_events=True)
    run_single(spec, trace=trace)

    departures = [e for e in trace.events
                  if e.event == "evict" and e.detail == "churn_leave"]
    assert departures, "nijedan churn odlazak nije zabelezen"

    # za svaki par (cvor, napadac): accept i evict moraju da se smenjuju, nikada
    # dva accept-a zaredom bez odlaska izmedju. Razmatraju se samo napadacki
    # identiteti (id >= n_honest), jer honest peer-ovi iz pocetne topologije stoje
    # u peer set-u od runde 0 i nemaju 'accept' dogadjaj.
    pairs = {}
    for e in trace.events:
        if (e.event in ("accept", "evict") and e.peer_id is not None
                and e.peer_id >= spec.n_honest):
            pairs.setdefault((e.node_id, e.peer_id), []).append(e)
    assert pairs, "nijedan napadac nikada nije primljen"
    for (node_id, peer), events in pairs.items():
        held = False
        for e in events:
            if e.event == "accept":
                assert not held, f"node {node_id} admitted {peer} twice with no eviction (r={e.round})"
                held = True
            else:
                assert held, f"node {node_id} evicted {peer} it was not holding (r={e.round})"
                held = False


def test_return_clears_observation_log_of_others():
    # povratak kao nov identitet: za svaki drugi cvor istorija krece iznova
    from identity.observation import Observation
    world = build_world(_spec())
    churn = world.scenario._churn()
    ctx = world.scenario.ctx

    round_no = next(r for r in range(1, 20) if churn.returning_ids(ctx, r))
    returner = churn.returning_ids(ctx, round_no)[0]
    node = world.nodes[0]
    node.observations[returner] = Observation(
        first_seen_round=0, last_seen_round=round_no - 1,
        successful_exchanges=9, missed_total=4)

    world.scenario.before_round(world.nodes, round_no)

    obs = node.observations[returner]
    assert obs.first_seen_round == round_no
    assert obs.successful_exchanges == 0 and obs.missed_total == 0


def test_no_reset_before_attack_activation():
    # regresija: before_round mora da postuje activate_round, isto kao responds i
    # broadcast_value. Inace bi se zapis o napadacu brisao jos tokom warmup faze,
    # iako napadac jos nigde nije otisao.
    from core import round_ops
    world = build_world(_spec(activate_round=11, churn_period=4, num_rounds=20))
    attacker = sorted(world.byzantine | world.sybil)[0]
    node = world.nodes[0]
    round_ops.observe(node, attacker, 1, exchanged=True)
    node.observations[attacker].missed_total = 7

    for r in range(1, 11):
        world.scenario.before_round(world.nodes, r)
        obs = node.observations[attacker]
        assert obs.first_seen_round == 1, f"log wiped in round {r}, before activation"
        assert obs.missed_total == 7
        assert world.scenario.returning_count(r) == 0

    # posle aktivacije reset se stvarno desava i zapis ga prijavljuje
    was_reset = False
    for r in range(11, 20):
        before = node.observations[attacker].first_seen_round
        world.scenario.before_round(world.nodes, r)
        if node.observations[attacker].first_seen_round != before:
            assert world.scenario.returning_count(r) > 0, (
                f"round {r}: a reset happened but the trace does not count it")
            was_reset = True
    assert was_reset, "posle aktivacije reset se nikada nije desio"


def test_longer_absence_follows_churn_offline():
    # churn_offline je jedina rucica za duzinu odsustva; povratak je i dalje
    # besplatan, jer je nonce resen unapred (vidi ogranicenje u 4.11)
    short = build_world(_spec(churn_period=6, churn_offline=1))
    long_ = build_world(_spec(churn_period=6, churn_offline=3))
    attacker = sorted(short.byzantine | short.sybil)[0]
    a = sum(1 for r in range(1, 25) if not short.scenario.responds(attacker, r, None))
    b = sum(1 for r in range(1, 25) if not long_.scenario.responds(attacker, r, None))
    assert b > a, f"churn_offline did not lengthen the absence ({b} vs {a})"


def test_disabled_churn_changes_nothing():
    # uz churn_period=0 modul uopste nije aktivan i niko nikada nije odsutan
    world = build_world(_spec(churn_period=0))
    assert not world.scenario._churn().enabled(world.scenario.ctx)
    attackers = sorted(world.byzantine | world.sybil)
    assert all(world.scenario.responds(i, r, None)
               for i in attackers for r in range(1, 21)), (
        "an attacker is away even though churn is not enabled")


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("OK - churn attack tests pass")