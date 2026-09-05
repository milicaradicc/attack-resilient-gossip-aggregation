from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import messages
from core.config import spec_from
from experiments.matrix import run_single


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


def test_counter_separates_classes():
    counter = messages.MessageCounter()
    counter.add_all([messages.control(messages.PEER_EXCHANGE, 1, 0, 2),
                     messages.control(messages.PEER_REJECT, 1, 0, 3),
                     messages.data(1, 2, 10.0)])
    assert counter.control == 2 and counter.data == 1


def test_defense_raises_control_but_not_data():
    # 5.1.5: zastita povecava control saobracaj, dok agregacione poruke ostaju iste
    base = dict(n_honest=20, beta=0.3, aggregation="trimmed_mean", seed=1)
    plain = run_single(spec_from(overlay="random", **base))
    guarded = run_single(spec_from(overlay="eclipse_resistant", **base))
    assert guarded.control_overhead(20) > plain.control_overhead(20)
    assert abs(guarded.data_overhead(20) - plain.data_overhead(20)) < 1e-9


def test_all_control_types_are_used():
    from core.setup import build_world
    from core.engine import Engine
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
           get_strategy(spec.overlay, spec.peer_set_size, world.registry, world.id_params),
           world.scenario, spec.num_rounds, metrics,
           make_rng(spec.seed, "matrix", spec.overlay, spec.aggregation),
           timeout_rounds=spec.timeout_rounds).run()
    # discovery, admission, odbijanje i heartbeat svi doprinose control saobracaju
    assert any(r.offered > 0 for r in metrics.rows)
    assert any(r.rejected > 0 for r in metrics.rows)
    assert all(r.control_msgs >= r.offered for r in metrics.rows if r.round >= 1)


if __name__ == "__main__":
    test_message_has_required_fields()
    test_control_and_data_are_distinguished()
    test_counter_separates_classes()
    test_defense_raises_control_but_not_data()
    test_all_control_types_are_used()
    print("OK — razdvajanje control i data saobracaja (5.1.5) prolazi")