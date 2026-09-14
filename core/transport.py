from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from core import messages
from core.messages import CONTROL, DATA, Message

# 5.1.5: the transport layer every message passes through. The sender hands the
# message to the transport, and the receiver picks it up when that phase of the
# round comes around. Since the tick-barrier model requires everyone to send
# first and only then read, delivery does not depend on the order in which nodes
# are processed.
#
# Protocol actions are exposed as named methods (request_peers, offer, accept,
# reject, probe, send_value), so that the code reads as what is being sent instead of
# leaving it to be guessed from the arguments. Every action builds the matching
# message and hands it to the same delivery and counting mechanism.
#
# Messages the receiver never picks up - rejections addressed to malicious
# identities, which do not read them - still count towards traffic, because in a
# real system they are messages that were sent.
#
# There is deliberately no eviction message. Dropping a peer from the peer set is
# a purely local decision: the node simply stops selecting it, and the peer finds
# out because the heartbeats stop. Announcing it would be traffic no gossip
# overlay actually sends. The eviction is still recorded in the event log
# (metrics/event_trace.py), which is a record of what happened, not of what was
# put on the wire.


class Transport:
    def __init__(self):
        self._mailboxes: Dict[int, List[Message]] = defaultdict(list)
        self._by_kind: Dict[str, int] = {CONTROL: 0, DATA: 0}
        self._by_type: Dict[str, int] = defaultdict(int)

    # --- sending and receiving --------------------------------------------

    def send(self, message: Message) -> None:
        # a message with no destination is counted, but there is nobody to deliver it to
        if message.target is not None:
            self._mailboxes[message.target].append(message)
        self._by_kind[message.kind] += 1
        self._by_type[message.type] += 1

    def receive(self, node_id: int, msg_type: str = None) -> List[Message]:
        # takes the messages for this node and removes them from the mailbox; with
        # a type given it takes only messages of that type and leaves the rest for
        # a later phase
        mailbox = self._mailboxes.get(node_id)
        if not mailbox:
            return []
        if msg_type is None:
            self._mailboxes[node_id] = []
            return mailbox
        taken = [m for m in mailbox if m.type == msg_type]
        self._mailboxes[node_id] = [m for m in mailbox if m.type != msg_type]
        return taken

    # --- protocol actions --------------------------------------------------

    def request_peers(self, round_now: int, node_id: int, to: int = None) -> None:
        # the node asks for new candidates; the answer arrives as a series of
        # peer_exchange messages. 'to' is None when the request goes to the peer
        # sampling service, which is not a node in the system - such a message is
        # counted, but there is nobody to deliver it to.
        self.send(messages.control(messages.PEER_REQUEST, round_now,
                                   node_id, target=to))

    def offer(self, round_now: int, candidate: int, to_node: int,
              nonce: int = None) -> None:
        # the candidate advertises itself to the node that decides on admission,
        # and carries its own PoW nonce as part of the offer - the receiver
        # verifies it straight from the message, asking no registry
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

    # --- measurement -------------------------------------------------------

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