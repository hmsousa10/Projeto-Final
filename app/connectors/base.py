"""Contract implemented by trusted business API connectors."""
from typing import Protocol


class StalePayload(ValueError):
    """The provider response is valid but outside the accepted time window."""


class Connector(Protocol):
    id: str
    label: str
    summary_kind: str

    def normalize(self, payload: object, company_id: str) -> dict: ...
