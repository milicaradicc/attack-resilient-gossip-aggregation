from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import spec_from
from in_process.matrix import run_single
from metrics.event_trace import (ACCEPT, ATTACK, BROADCAST, CHURN, EVICT, FLOOD,
                                 REJECT, TRACE_FIELDS, EventTrace)


def _spec(overlay="eclipse_resistant"):
    return spec_from(n_honest=12, beta=0.3, overlay=overlay, aggregation="trimmed_mean",
                     seed=1, num_rounds=20, activate_round=1, pow_difficulty_bits=8,
                     trace_events=True)


def test_trace_records_admission_decisions():
    # 5.1.8: zapis mora sadrzati i prihvatanja i odbijanja kandidata
    trace = EventTrace()
    run_single(_spec(), trace=trace)
    events = {e.event for e in trace.events}
    assert ACCEPT in events and REJECT in events


def test_trace_records_attack_activation():
    trace = EventTrace()
    run_single(_spec(), trace=trace)
    activations = [e for e in trace.events if e.event == ATTACK]
    assert len(activations) == 1
    assert activations[0].round == 1


def test_trace_records_peer_set_changes():
    # promena peer set-a: izbacivanje peer-a mora biti zabelezeno
    trace = EventTrace()
    run_single(_spec(overlay="random"), trace=trace)
    assert any(e.event == EVICT for e in trace.events)


def test_rejection_reasons_are_named():
    trace = EventTrace()
    run_single(_spec(), trace=trace)
    reasons = {e.detail for e in trace.events if e.event == REJECT}
    assert reasons & {"invalid_pow", "too_young", "low_score", "bucket_full"}


def test_trace_records_attacker_activity():
    # 5.1.8: napadacke aktivnosti — emitovane vrednosti, churn i flooding
    trace = EventTrace()
    spec = _spec()
    spec.flooding = 5
    spec.churn_period = 4
    run_single(spec, trace=trace)
    events = {e.event for e in trace.events}
    assert BROADCAST in events and CHURN in events and FLOOD in events
    emitted = [e for e in trace.events if e.event == BROADCAST]
    assert all(e.value == spec.coordinated_value for e in emitted)


def test_csv_rows_match_fields():
    trace = EventTrace()
    run_single(_spec(), trace=trace)
    rows = trace.csv_rows()
    assert rows and all(len(r) == len(TRACE_FIELDS) for r in rows)


def test_trace_off_by_default():
    metrics = run_single(spec_from(n_honest=10, beta=0.0))
    assert metrics.rows


if __name__ == "__main__":
    test_trace_records_admission_decisions()
    test_trace_records_attack_activation()
    test_trace_records_peer_set_changes()
    test_rejection_reasons_are_named()
    test_trace_records_attacker_activity()
    test_csv_rows_match_fields()
    test_trace_off_by_default()
    print("OK — zapis dogadjaja (5.1.8) prolazi")