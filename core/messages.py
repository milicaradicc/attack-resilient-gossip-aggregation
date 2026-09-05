from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# 5.1.5: sistem razlikuje dve klase poruka — control plane i data plane.
# Svaka poruka nosi tip, identifikator runde, izvorni identitet i payload,
# cime se overhead zastitnih mehanizama meri odvojeno od same gossip razmene.

CONTROL = "control"
DATA = "data"

# tipovi control poruka
PEER_EXCHANGE = "peer_exchange"   # ponuda kandidata kroz discovery
ADMISSION = "admission"           # provera i prihvatanje kandidata
PEER_REJECT = "peer_reject"       # odbijanje kandidata
HEARTBEAT = "heartbeat"           # provera aktivnosti peer-a

# tip data poruke
AGGREGATE = "aggregate"           # agregaciona vrednost


@dataclass
class Message:
    kind: str          # control ili data
    type: str          # konkretan tip poruke
    round: int         # identifikator runde
    source: int        # identitet posiljaoca
    payload: Any = None
    target: Optional[int] = None

    @property
    def is_control(self) -> bool:
        return self.kind == CONTROL

    @property
    def is_data(self) -> bool:
        return self.kind == DATA


def control(msg_type: str, round_now: int, source: int,
            target: int = None, payload: Any = None) -> Message:
    return Message(CONTROL, msg_type, round_now, source, payload, target)


def data(round_now: int, source: int, value: float, target: int = None) -> Message:
    return Message(DATA, AGGREGATE, round_now, source, value, target)


@dataclass
class MessageCounter:
    # broji stvarne poruke po klasi, umesto da se overhead racuna formulom
    control: int = 0
    data: int = 0

    def add(self, message: Message) -> None:
        if message.is_control:
            self.control += 1
        else:
            self.data += 1

    def add_all(self, messages) -> None:
        for message in messages:
            self.add(message)