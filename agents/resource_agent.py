"""
Resource Agent

Job: manage the warehouse inventory safely.
  * Receives aid convoys (new stock) each round.
  * Answers ALLOCATION_REQUEST messages from the Distribution Agent.
  * NEVER lets inventory go below zero: if a request asks for more than
    what is in stock, the request is scaled down to what is available.
  * Sends INVENTORY_REPORT messages so other agents know current stock.
"""

from agents.base_agent import BaseAgent
from agents.config import RESOURCES
from agents.messaging import ALLOCATION_REQUEST, ALLOCATION_RESPONSE, INVENTORY_REPORT


class ResourceAgent(BaseAgent):
    def __init__(self):
        super().__init__("ResourceAgent")
        self.inventory = {r: 0 for r in RESOURCES}        # current stock
        self.total_received = {r: 0 for r in RESOURCES}   # all stock ever received
        self.total_released = {r: 0 for r in RESOURCES}   # all stock given out
        self.rejected_units = {r: 0 for r in RESOURCES}   # units refused (over-requests)

    def receive_convoy(self, shipment: dict, round_number: int):
        """Add a new shipment of aid to the warehouse."""
        self.current_round = round_number
        for resource, qty in shipment.items():
            qty = max(0, int(qty))  # ignore negative or invalid quantities
            self.inventory[resource] += qty
            self.total_received[resource] += qty

    def report_inventory(self):
        """Tell the Distribution and Monitoring agents how much stock is available."""
        content = {
            "inventory": dict(self.inventory),
            "summary": ", ".join(f"{r}: {q:,}" for r, q in self.inventory.items()),
        }
        self.send("DistributionAgent", INVENTORY_REPORT, content)
        self.send("MonitoringAgent", INVENTORY_REPORT, content)

    def step(self, round_number: int):
        """Answer every allocation request waiting in the inbox."""
        self.current_round = round_number
        for request in self.read_messages(ALLOCATION_REQUEST):
            approved = self.approve_request(request.content["plan"])
            total = {r: sum(a.get(r, 0) for a in approved.values()) for r in RESOURCES}
            self.send(
                request.sender,
                ALLOCATION_RESPONSE,
                {
                    "approved": approved,
                    "summary": "Approved - " + ", ".join(f"{r}: {q:,}" for r, q in total.items()),
                },
            )
        # After releasing stock, let everyone know the new inventory
        self.send(
            "MonitoringAgent",
            INVENTORY_REPORT,
            {
                "inventory": dict(self.inventory),
                "summary": "After distribution - "
                + ", ".join(f"{r}: {q:,}" for r, q in self.inventory.items()),
            },
        )

    def approve_request(self, plan: dict) -> dict:
        """
        Check a distribution plan against the inventory and release the stock.

        plan = {area_id: {resource: quantity}}
        Returns the approved plan (same shape). If the plan asks for more than
        the stock, every area's share is reduced so the total fits the stock.
        """
        approved = {area: {} for area in plan}
        for resource in RESOURCES:
            requested = {area: max(0, int(items.get(resource, 0))) for area, items in plan.items()}
            total_requested = sum(requested.values())
            available = self.inventory[resource]

            if total_requested <= available:
                granted = requested
            else:
                # Over-allocation protection: scale everything down to fit.
                ratio = available / total_requested
                granted = {area: int(qty * ratio) for area, qty in requested.items()}
                self.rejected_units[resource] += total_requested - sum(granted.values())

            for area, qty in granted.items():
                approved[area][resource] = qty
            released = sum(granted.values())
            self.inventory[resource] -= released
            self.total_released[resource] += released

            # Safety check: inventory can never be negative
            assert self.inventory[resource] >= 0, f"Negative inventory for {resource}!"
        return approved
