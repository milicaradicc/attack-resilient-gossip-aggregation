from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from core import messages
from core.messages import CONTROL, DATA, Message


class Transport:
    def __init__(self):
        self._mailboxes: Dict[int, List[Message]] = defaultdict(list)
        self._by_kind: Dict[str, int] = {CONTROL: 0, DATA: 0}
        self._by_type: Dict[str, int] = defaultdict(int)

    def send(self, message: Message) -> None:
        if message.target is not None:
            self._mailboxes[message.target].append(message)
        self._by_kind[message.kind] += 1
        self._by_type[message.type] += 1

    def receive(self, node_id: int, msg_type: str = None) -> List[Message]:
        mailbox = self._mailboxes.get(node_id)
        if not mailbox:
            return []
        if msg_type is None:
            self._mailboxes[node_id] = []
            return mailbox
        taken = [m for m in mailbox if m.type == msg_type]
        self._mailboxes[node_id] = [m for m in mailbox if m.type != msg_type]
        return taken

    def request_peers(self, round_now: int, node_id: int, to: int = None) -> None:
        self.send(messages.control(messages.PEER_REQUEST, round_now,
                                   node_id, target=to))

    def offer(self, round_now: int, candidate: int, to_node: int,
              nonce: int = None) -> None:
        self.send(messages.control(messages.PEER_EXCHANGE, round_now,
                                   candidate, target=to_node, payload=nonce))

    def accept(self, round_now: int, node_id: int, candidate: int) -> None:
        self.send(messages.control(messages.ADMISSION, round_now,
                                   node_id, target=candidate))

    def reject(self, round_now: int, node_id: int, candidate: int,
               reason: str) -> None:
        self.send(messages.control(messages.PEER_REJECT, round_now,
                                   node_id, target=candidate, payload=reason))

    def probe(self, round_now: int, node_id: int, peer: int) -> None:
        self.send(messages.control(messages.HEARTBEAT, round_now,
                                   node_id, target=peer))

    def send_value(self, round_now: int, source: int, target: int,
                   value: float) -> None:
        self.send(messages.data(round_now, source, value, target=target))

    @property
    def control(self) -> int:
        return self._by_kind[CONTROL]

    @property
    def data(self) -> int:
        return self._by_kind[DATA]

    def count(self, msg_type: str) -> int:
        return self._by_type[msg_type]

    def undelivered(self) -> int:
        return sum(len(v) for v in self._mailboxes.values())