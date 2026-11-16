"""
Messaging system used by all agents.

Agents never call each other's methods directly. Instead they send
Message objects through a shared MessageBus. The bus delivers each message
to the receiver's inbox and keeps a full log, so the dashboard can show
exactly how the agents talked to each other.
"""

from dataclasses import dataclass, field
from datetime import datetime


# Message types used in the system (kept in one place to avoid typos)
INVENTORY_REPORT = "INVENTORY_REPORT"
NEEDS_REPORT = "NEEDS_REPORT"
PRIORITY_REPORT = "PRIORITY_REPORT"
ALLOCATION_REQUEST = "ALLOCATION_REQUEST"
ALLOCATION_RESPONSE = "ALLOCATION_RESPONSE"
DELIVERY_REPORT = "DELIVERY_REPORT"
ALERT = "ALERT"


@dataclass
class Message:
    """A single message sent from one agent to another."""

    sender: str
    receiver: str
    msg_type: str
    content: dict
    round_number: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def summary(self) -> str:
        """Short human-readable description of the message (used in the log)."""
        return self.content.get("summary", "")


class MessageBus:
    """Delivers messages between registered agents and records every message."""

    def __init__(self):
        self.agents = {}   # agent name -> agent object
        self.log = []      # every message ever sent, in order

    def register(self, agent):
        """Add an agent to the bus so it can send and receive messages."""
        self.agents[agent.name] = agent
        agent.bus = self

    def send(self, message: Message):
        """Deliver a message to its receiver's inbox and save it in the log."""
        if message.receiver not in self.agents:
            raise ValueError(f"Unknown receiver: {message.receiver}")
        self.log.append(message)
        self.agents[message.receiver].inbox.append(message)

    def log_as_records(self) -> list:
        """Return the message log as a list of dictionaries (easy to show as a table)."""
        return [
            {
                "Round": m.round_number,
                "Time": m.timestamp,
                "From": m.sender,
                "To": m.receiver,
                "Type": m.msg_type,
                "Summary": m.summary(),
            }
            for m in self.log
        ]
