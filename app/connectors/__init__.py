"""Trusted connector registry. Deployment configuration selects code, never imports it."""
from types import MappingProxyType

from .base import Connector, StalePayload
from .orders import OrdersSummaryV1


# Only reviewed application code belongs here; configuration cannot load Python modules.
CONNECTORS = MappingProxyType({'orders-summary-v1': OrdersSummaryV1()})


def get_connector(connector_id: str) -> Connector:
    if connector_id not in CONNECTORS:
        raise RuntimeError('Conector empresarial desconhecido; escolhe um conector instalado e suportado.')
    return CONNECTORS[connector_id]
