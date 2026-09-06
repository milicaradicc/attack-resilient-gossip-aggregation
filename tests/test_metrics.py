from __future__ import annotations

import csv
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from attacks.scenario import AttackParams, Scenario
from core.config import spec_from
from in_process.matrix import CONFIG_FIELDS, SUMMARY_FIELDS, run_matrix, run_single
from metrics.experiment_metrics import FIELDS, NODE_FIELDS, ExperimentMetrics, RoundCounters

# 5.2.9. Validacija metrike i eksport sistema
# Proverava se tacnost obracuna metrika nad poznatim vrednostima, ispravnost
# CSV/JSON eksporta, konzistentnost round identifier-a i integritet trace podataka.


class _Node:
    def __init__(self, estimate, peers):
        self.estimate = estimate
        self.peers = list(peers)


def _scenario(honest, byzantine, sybil):
    return Scenario(set(honest), set(byzantine), set(sybil),
                    AttackParams(activate_round=1))


def test_error_and_spread_over_known_values():
    # 6.3.1: greska se racuna PO CVORU pa usrednjava, ne kao greska proseka.
    # x* = 100; procene 98, 100, 102 -> odstupanja 2, 0, 2 -> E = (0.02+0+0.02)/3
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    nodes = {0: _Node(98.0, [1]), 1: _Node(100.0, [0]), 2: _Node(102.0, [0])}
    row = metrics.record(1, nodes, _scenario([0, 1, 2], [], []), RoundCounters())
    assert abs(row.avg_estimate - 100.0) < 1e-9
    assert abs(row.err_rel - 0.04 / 3.0) < 1e-9
    assert abs(row.spread - 4.0) < 1e-9


def test_error_is_average_of_node_errors_not_error_of_average():
    # razlika se vidi kada odstupanja imaju suprotan znak: greska proseka bi bila 0
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    nodes = {0: _Node(90.0, [1]), 1: _Node(110.0, [0])}
    row = metrics.record(1, nodes, _scenario([0, 1], [], []), RoundCounters())
    assert abs(row.avg_estimate - 100.0) < 1e-9
    assert abs(row.err_rel - 0.1) < 1e-9


def test_sybil_penetration_over_known_peer_sets():
    # cvor 0: 2 od 4 suseda su Sybil -> 0.5; cvor 1: 0 od 2 -> 0.0; prosek 0.25
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    nodes = {0: _Node(100.0, [1, 2, 10, 11]), 1: _Node(100.0, [0, 2])}
    row = metrics.record(1, nodes, _scenario([0, 1, 2], [], [10, 11]), RoundCounters())
    assert abs(row.sybil_penetration - 0.25) < 1e-9


def test_eclipse_rate_over_known_peer_sets():
    # cvor 0 nema nijednog honest suseda -> eclipsed; 1 od 2 cvora = 0.5
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    nodes = {0: _Node(100.0, [10, 11]), 1: _Node(100.0, [0])}
    row = metrics.record(1, nodes, _scenario([0, 1], [], [10, 11]), RoundCounters())
    assert abs(row.eclipse_rate - 0.5) < 1e-9


def test_counters_are_carried_through():
    # brojaci poruka i razloga odbijanja moraju stici u zapis nepromenjeni
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    counters = RoundCounters(data_msgs=7, control_msgs=13, offered=5, rejected=3,
                             rej_invalid_pow=1, rej_too_young=1, rej_low_score=1,
                             rej_bucket_full=0, timeouts=2)
    row = metrics.record(1, {0: _Node(100.0, [1])},
                         _scenario([0, 1], [], []), counters)
    assert (row.data_msgs, row.control_msgs) == (7, 13)
    assert (row.offered, row.rejected, row.timeouts) == (5, 3, 2)
    assert row.rej_invalid_pow + row.rej_too_young + row.rej_low_score == 3


def test_rejection_breakdown_sums_to_one():
    metrics = run_single(spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                                   aggregation="trimmed_mean", seed=1, num_rounds=20,
                                   activate_round=1, pow_difficulty_bits=8))
    breakdown = metrics.rejection_breakdown()
    assert abs(sum(breakdown.values()) - 1.0) < 1e-9


def test_round_identifiers_are_consistent():
    # 5.2.9: round identifier mora ici 0..num_rounds bez preskoka i duplikata
    spec = spec_from(n_honest=10, beta=0.3, overlay="sybil_resistant",
                     aggregation="mean", seed=1, num_rounds=15, activate_round=1,
                     pow_difficulty_bits=8)
    metrics = run_single(spec)
    rounds = [r.round for r in metrics.rows]
    assert rounds == list(range(0, spec.num_rounds + 1))
    node_rounds = {r.round for r in metrics.node_rows}
    assert node_rounds <= set(rounds)


def test_convergence_time_measured_from_given_round():
    # 6.3.2: T = min{t : E(t) < eps}, pri cemu merenje pocinje od zadate runde.
    # Bez toga bi se merila konvergencija tokom warmup faze i rezultat bi bio
    # isti bez obzira na napad.
    spec = spec_from(n_honest=20, beta=0.3, overlay="random",
                     aggregation="trimmed_mean", seed=1)
    metrics = run_single(spec)
    od_pocetka = metrics.convergence_time(spec.epsilon, since=1)
    od_napada = metrics.convergence_time(spec.epsilon, since=spec.activate_round)
    assert od_pocetka >= 1, "tokom warmup-a sistem konvergira"
    assert od_napada == -1, "pod napadom bez zastite ne sme konvergirati"


def test_convergence_time_returns_sentinel_when_never_reached():
    metrics = ExperimentMetrics(x_star=100.0, num_buckets=8)
    for round_no in range(0, 5):
        metrics.record(round_no, {0: _Node(200.0, [1]), 1: _Node(200.0, [0])},
                       _scenario([0, 1], [], []), RoundCounters())
    assert metrics.convergence_time(0.05) == -1


def test_csv_and_json_export_agree():
    # 5.2.9: isti brojevi moraju stici i u CSV i u JSON izvoz
    config = os.path.join(ROOT, "configs", "tiny.json")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "e.csv")
        summary = out.replace(".csv", "_summary.csv")
        js = out.replace(".csv", ".json")
        run_matrix(config, out, summary, js)

        with open(summary) as f:
            csv_rows = list(csv.DictReader(f))
        with open(js) as f:
            runs = json.load(f)["runs"]

        assert len(csv_rows) == len(runs)
        for row, run in zip(csv_rows, runs):
            for field in SUMMARY_FIELDS:
                assert abs(float(row[field]) - float(run["summary"][field])) < 1e-9
            for field in CONFIG_FIELDS:
                assert str(row[field]) == str(run["config"][field])


def test_exported_headers_match_definitions():
    config = os.path.join(ROOT, "configs", "tiny.json")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "h.csv")
        run_matrix(config, out, out.replace(".csv", "_summary.csv"),
                   out.replace(".csv", ".json"))
        with open(out) as f:
            assert next(csv.reader(f)) == CONFIG_FIELDS + FIELDS
        with open(out.replace(".csv", "_summary.csv")) as f:
            assert next(csv.reader(f)) == CONFIG_FIELDS + SUMMARY_FIELDS
        nodes = out.replace(".csv", "_nodes.csv")
        if os.path.exists(nodes):
            with open(nodes) as f:
                assert next(csv.reader(f)) == CONFIG_FIELDS + NODE_FIELDS


def test_trace_integrity():
    # 5.2.9: integritet trace podataka — svaki dogadjaj pripada postojecoj rundi
    # i poznatom tipu, a broj kolona odgovara definiciji
    from metrics.event_trace import TRACE_FIELDS, EventTrace
    spec = spec_from(n_honest=12, beta=0.3, overlay="eclipse_resistant",
                     aggregation="trimmed_mean", seed=1, num_rounds=20,
                     activate_round=1, pow_difficulty_bits=8, trace_events=True)
    trace = EventTrace()
    run_single(spec, trace=trace)
    known = {"accept", "reject", "evict", "attack_activated", "estimate",
             "malicious_broadcast", "churn_reset", "flooding"}
    for event in trace.events:
        assert event.event in known, f"nepoznat tip dogadjaja: {event.event}"
        assert 0 <= event.round <= spec.num_rounds
    assert all(len(row) == len(TRACE_FIELDS) for row in trace.csv_rows())


if __name__ == "__main__":
    test_error_and_spread_over_known_values()
    test_error_is_average_of_node_errors_not_error_of_average()
    test_sybil_penetration_over_known_peer_sets()
    test_eclipse_rate_over_known_peer_sets()
    test_counters_are_carried_through()
    test_rejection_breakdown_sums_to_one()
    test_round_identifiers_are_consistent()
    test_convergence_time_measured_from_given_round()
    test_convergence_time_returns_sentinel_when_never_reached()
    test_csv_and_json_export_agree()
    test_exported_headers_match_definitions()
    test_trace_integrity()
    print("OK — validacija metrika i eksporta (5.2.9) prolazi")