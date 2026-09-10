from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from core.messages import CONTROL, DATA, Message


class Transport:
    def __init__(self):
        self._mailboxes: Dict[int, List[Message]] = defaultdict(list)
        self._by_kind: Dict[str, int] = {CONTROL: 0, DATA: 0}
        self._by_type: Dict[str, int] = defaultdict(int)

    def send(self, message: Message) -> None:
        # poruka bez odredista se broji, ali nema kome da se isporuci
        if message.target is not None:
            self._mailboxes[message.target].append(message)
        self._by_kind[message.kind] += 1
        self._by_type[message.type] += 1

    def send_all(self, messages) -> None:
        for message in messages:
            self.send(message)

    def receive(self, node_id: int, msg_type: str = None) -> List[Message]:
        # preuzima poruke za dati cvor i uklanja ih iz sanduceta; uz zadat tip
        # preuzima samo poruke tog tipa, a ostale ostavlja za narednu fazu
        mailbox = self._mailboxes.get(node_id)
        if not mailbox:
            return []
        if msg_type is None:
            self._mailboxes[node_id] = []
            return mailbox
        taken = [m for m in mailbox if m.type == msg_type]
        self._mailboxes[node_id] = [m for m in mailbox if m.type != msg_type]
        return taken

    @property
    def control(self) -> int:
        return self._by_kind[CONTROL]

    @property
    def data(self) -> int:
        return self._by_kind[DATA]

    def count(self, msg_type: str) -> int:
        return self._by_type[msg_type]

    def undelivered(self) -> int:
        # poruke koje niko nije preuzeo
        return sum(len(v) for v in self._mailboxes.values())