from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from core import messages
from core.messages import CONTROL, DATA, Message

# 5.1.5: transportni sloj kroz koji prolazi svaka poruka. Posiljalac je predaje
# transportu, a primalac je preuzima kada u rundi dodje red na tu fazu. Posto
# tick-barrier model nalaze da svi prvo posalju pa tek onda citaju, isporuka ne
# zavisi od redosleda obrade cvorova.
#
# Radnje protokola izlozene su kao imenovane metode (offer, accept, reject,
# evict, probe, send_value), da bi se iz koda citalo sta se salje umesto da se
# nasluti iz argumenata. Svaka radnja pravi odgovarajucu poruku i predaje je
# istom mehanizmu isporuke i brojanja.
#
# Poruke koje primalac ne preuzme — na primer odbijenice upucene napadackim
# identitetima, koji ih ne citaju — i dalje ulaze u brojanje saobracaja, jer u
# stvarnom sistemu predstavljaju poslate poruke.


class Transport:
    def __init__(self):
        self._mailboxes: Dict[int, List[Message]] = defaultdict(list)
        self._by_kind: Dict[str, int] = {CONTROL: 0, DATA: 0}
        self._by_type: Dict[str, int] = defaultdict(int)

    # --- slanje i preuzimanje ---------------------------------------------

    def send(self, message: Message) -> None:
        # poruka bez odredista se broji, ali nema kome da se isporuci
        if message.target is not None:
            self._mailboxes[message.target].append(message)
        self._by_kind[message.kind] += 1
        self._by_type[message.type] += 1

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

    # --- radnje protokola --------------------------------------------------

    def request_peers(self, round_now: int, node_id: int, to: int) -> None:
        # cvor traži nove kandidate; odgovor stize kao niz peer_exchange poruka
        self.send(messages.control(messages.PEER_REQUEST, round_now,
                                   node_id, target=to))

    def offer(self, round_now: int, candidate: int, to_node: int,
              nonce: int = None) -> None:
        # kandidat se reklamira cvoru koji odlucuje o prijemu, i nosi
        # sopstveni PoW nonce kao deo ponude — primalac ga verifikuje
        # direktno iz poruke, ne pita nikakav registar
        self.send(messages.control(messages.PEER_EXCHANGE, round_now,
                                   candidate, target=to_node, payload=nonce))

    def accept(self, round_now: int, node_id: int, candidate: int) -> None:
        self.send(messages.control(messages.ADMISSION, round_now,
                                   node_id, target=candidate))

    def reject(self, round_now: int, node_id: int, candidate: int,
               reason: str) -> None:
        self.send(messages.control(messages.PEER_REJECT, round_now,
                                   node_id, target=candidate, payload=reason))

    def evict(self, round_now: int, node_id: int, peer: int, reason: str) -> None:
        # uklanjanje iz peer set-a: sused se obavestava da vise nije u skupu
        self.send(messages.control(messages.PEER_EVICT, round_now,
                                   node_id, target=peer, payload=reason))

    def probe(self, round_now: int, node_id: int, peer: int) -> None:
        self.send(messages.control(messages.HEARTBEAT, round_now,
                                   node_id, target=peer))

    def send_value(self, round_now: int, source: int, target: int,
                   value: float) -> None:
        self.send(messages.data(round_now, source, value, target=target))

    # --- merenje -----------------------------------------------------------

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