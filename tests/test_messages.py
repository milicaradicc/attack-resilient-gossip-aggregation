from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import messages
from core.config import spec_from
from in_process.matrix import run_single


def test_message_has_required_fields():
    # 5.1.5: svaka poruka nosi tip, rundu, izvor i payload
    m = messages.data(round_now=3, source=7, value=99.5)
    assert m.type == messages.AGGREGATE and m.round == 3
    assert m.source == 7 and m.payload == 99.5


def test_control_and_data_are_distinguished():
    c = messages.control(messages.HEARTBEAT, 2, 1, target=4)
    d = messages.data(2, 1, 50.0)
    assert c.is_control and not c.is_data
    assert d.is_data and not d.is_control


def test_transport_separates_classes():
    # 5.1.5: transportni sloj broji poruke po klasi
    from core.transport import Transport
    t = Transport()
    t.offer(1, 0, 2)
    t.reject(1, 0, 3, "too_young")
    t.send_value(1, 2, 0, 10.0)
    assert t.control == 2 and t.data == 1


def test_transport_delivers_to_mailbox():
    # posiljalac je ostavlja, primalac je uzima iz sopstvenog sanducica
    from core.transport import Transport
    t = Transport()
    t.send(messages.data(1, 5, 42.0, target=3))
    t.send(messages.data(1, 6, 7.0, target=9))
    for_three = t.receive(3)
    assert len(for_three) == 1 and for_three[0].source == 5 and for_three[0].payload == 42.0
    assert t.receive(3) == [], "the mailbox is emptied once read"


def test_transport_filters_by_type():
    # jedna faza runde uzima samo svoj tip poruke; ostalo ceka
    from core.transport import Transport
    t = Transport()
    t.send(messages.control(messages.PEER_EXCHANGE, 1, 8, target=0))
    t.send(messages.data(1, 9, 5.0, target=0))
    offers = t.receive(0, messages.PEER_EXCHANGE)
    assert len(offers) == 1 and offers[0].type == messages.PEER_EXCHANGE
    assert len(t.receive(0, messages.AGGREGATE)) == 1


def test_unread_messages_still_counted():
    # odbijenice poslate napadacima niko ne preuzima, ali se i dalje broje
    from core.transport import Transport
    t = Transport()
    t.send(messages.control(messages.PEER_REJECT, 1, 0, target=99, payload="too_young"))
    assert t.control == 1
    assert t.undelivered() == 1


def test_defense_raises_control_but_not_data():
    # 5.1.5: odbrana podize kontrolni saobracaj dok agregacione poruke ostaju iste
    base = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1)
    plain = run_single(spec_from(overlay="random", **base))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **base))
    assert guarded.control_overhead(20) > plain.control_overhead(20)
    assert abs(guarded.data_overhead(20) - plain.data_overhead(20)) < 1e-9


def test_value_travels_as_addressed_message():
    # 5.1.5: agregaciona vrednost putuje kao poruka od suseda ka cvoru, sa
    # upisanim izvorom i odredistem
    from core import round_ops
    from core.transport import Transport

    class _N:
        node_id = 3
        peers = [1, 2]

    t = Transport()
    emitted = {1: 10.0, 2: 20.0, 9: 99.0}
    round_ops.deliver(_N(), [1, 2], emitted, round_now=4, transport=t)
    received = t.receive(3, messages.AGGREGATE)
    assert len(received) == 2
    for message, source in zip(received, [1, 2]):
        assert message.is_data
        assert message.source == source
        assert message.target == 3
        assert message.round == 4
        assert message.payload == emitted[source]


def test_unknown_peer_sends_nothing():
    # lazni identiteti (flooding) nemaju emitovanu vrednost, pa ne salju poruku
    from core import round_ops
    from core.transport import Transport

    class _N:
        node_id = 0
        peers = [1, 10001]

    t = Transport()
    round_ops.deliver(_N(), [1, 10001], {1: 5.0}, round_now=2, transport=t)
    received = t.receive(0, messages.AGGREGATE)
    assert len(received) == 1 and received[0].source == 1


def test_named_actions_produce_expected_types():
    # protokolarne akcije su imenovane i svaka sastavlja poruku sopstvenog tipa
    from core.transport import Transport
    t = Transport()
    t.offer(1, 8, 0)
    t.accept(1, 0, 8)
    t.reject(1, 0, 9, "low_score")
    t.probe(1, 0, 2)
    t.send_value(1, 2, 0, 3.5)
    assert t.count(messages.PEER_EXCHANGE) == 1
    assert t.count(messages.ADMISSION) == 1
    assert t.count(messages.PEER_REJECT) == 1
    assert t.count(messages.HEARTBEAT) == 1
    assert t.count(messages.AGGREGATE) == 1
    assert t.control == 4 and t.data == 1
    assert not hasattr(t, "evict"), (
        "eviction is a local decision and must not put a message on the wire")


def test_discovery_is_request_and_response():
    # 5.1.5: cvor salje zahtev za kandidatima, a ponude stizu kao zasebne poruke
    # od identiteta koji se reklamira; admit ih uzima iz sanducica. Dve polovine
    # su odvojeni pozivi bas zato da cvor ne moze da drzi odgovor pre nego sto je
    # pitao.
    from core import round_ops
    from core.transport import Transport

    class _N:
        node_id = 0
        peers = []

    t = Transport()
    node = _N()
    # prva polovina: cvor salje zahtev i jos nista ne zna
    round_ops.send_peer_request(node, round_now=3, transport=t)
    assert t.count(messages.PEER_REQUEST) == 1, "the request is a single message"
    assert t.receive(0, messages.PEER_EXCHANGE) == [], (
        "the node must not hold candidates before the answer arrives")
    # druga polovina: odgovor stize kao poruke, svaka sa sopstvenim PoW nonce-om
    round_ops.receive_offers(node, [(5, 111), (9, 222)], round_now=3, transport=t)
    offers = t.receive(0, messages.PEER_EXCHANGE)
    assert [m.source for m in offers] == [5, 9], "the source is the identity being offered"
    assert [m.payload for m in offers] == [111, 222], "the nonce arrives in the message itself"
    assert all(m.target == 0 and m.round == 3 for m in offers)


def test_all_control_types_are_used():
    from core.setup import build_world
    from in_process.engine import Engine
    from core.rng import make_rng
    from aggregation import get_aggregation
    from metrics.experiment_metrics import ExperimentMetrics
    from sampling import get_strategy
    spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=1, num_rounds=20,
                     activate_round=1, pow_difficulty_bits=8)
    world = build_world(spec)
    metrics = ExperimentMetrics(x_star=world.x_star, num_buckets=spec.num_buckets)
    Engine(world.nodes, get_aggregation("trimmed_mean", alpha=spec.trim_alpha),
           get_strategy(spec.overlay, spec.peer_set_size, world.id_params),
           world.scenario, spec.num_rounds, metrics,
           make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation),
           world.nonces, timeout_rounds=spec.timeout_rounds).run()
    # discovery, admission, odbijanje i heartbeat doprinose kontrolnom saobracaju
    assert any(r.offered > 0 for r in metrics.rows)
    assert any(r.rejected > 0 for r in metrics.rows)
    assert all(r.control_msgs >= r.offered for r in metrics.rows if r.round >= 1)


if __name__ == "__main__":
    test_message_has_required_fields()
    test_control_and_data_are_distinguished()
    test_transport_separates_classes()
    test_transport_delivers_to_mailbox()
    test_transport_filters_by_type()
    test_unread_messages_still_counted()
    test_defense_raises_control_but_not_data()
    test_value_travels_as_addressed_message()
    test_unknown_peer_sends_nothing()
    test_named_actions_produce_expected_types()
    test_discovery_is_request_and_response()
    test_all_control_types_are_used()
    print("OK - the control/data traffic split (5.1.5) passes")