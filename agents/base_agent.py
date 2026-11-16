"""
BaseAgent: the parent class for all five agents.

It gives every agent:
  * a name
  * an inbox (list of received messages)
  * a send() helper to talk to other agents through the MessageBus
  * a read_messages() helper to pick messages of a given type from the inbox
"""

from agents.messaging import Message


class BaseAgent:
    def __init__(self, name: str):
        self.name = name
        self.inbox = []
        self.bus = None          # set automatically by MessageBus.register()
        self.current_round = 0

    def send(self, receiver: str, msg_type: str, content: dict):
        """Send a message to another agent."""
        if self.bus is None:
            raise RuntimeError(f"{self.name} is not registered on a message bus")
        message = Message(
            sender=self.name,
            receiver=receiver,
            msg_type=msg_type,
            content=content,
            round_number=self.current_round,
        )
        self.bus.send(message)

    def read_messages(self, msg_type: str) -> list:
        """Remove and return all inbox messages of the given type (oldest first)."""
        matching = [m for m in self.inbox if m.msg_type == msg_type]
        self.inbox = [m for m in self.inbox if m.msg_type != msg_type]
        return matching

    def latest_message(self, msg_type: str):
        """Return only the newest message of a type (or None if there is none)."""
        messages = self.read_messages(msg_type)
        return messages[-1] if messages else None
