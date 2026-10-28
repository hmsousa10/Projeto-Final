"""Validated orders-summary-v1 connector, used by the Aurora reference API."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..models import Input
from .base import StalePayload


class OrderCounts(Input):
    total: int = Field(strict=True, ge=0, le=1_000_000)
    preparing: int = Field(strict=True, ge=0, le=1_000_000)
    shipped: int = Field(strict=True, ge=0, le=1_000_000)
    delivered: int = Field(strict=True, ge=0, le=1_000_000)

    @model_validator(mode='after')
    def consistent(self):
        if self.total != self.preparing + self.shipped + self.delivered:
            raise ValueError('Totais incoerentes')
        return self


class BusinessSummary(Input):
    schema_version: int = Field(strict=True, ge=1, le=1)
    company_id: str = Field(pattern=r'^[a-z0-9-]{1,40}$')
    company_name: str = Field(min_length=1, max_length=100)
    environment: Literal['laboratory', 'production']
    generated_at: datetime
    orders: OrderCounts

    @field_validator('generated_at', mode='before')
    @classmethod
    def timestamp_text(cls, value):
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError('Instante ISO esperado')
        return value


class OrdersSummaryV1:
    id = 'orders-summary-v1'
    label = 'Resumo de encomendas · v1'
    summary_kind = 'orders'

    def normalize(self, payload, company_id):
        body = BusinessSummary.model_validate(payload)
        if body.company_id != company_id or body.generated_at.tzinfo is None:
            raise ValueError('Identidade ou instante inválido')
        age = (datetime.now(timezone.utc) - body.generated_at).total_seconds()
        if not -30 <= age <= 120:
            raise StalePayload()
        return body.model_dump(mode='json')
