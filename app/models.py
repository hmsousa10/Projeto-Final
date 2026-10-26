from typing import Literal, Annotated
import re

from pydantic import BaseModel, Field, StringConstraints, AfterValidator, field_validator

Password = Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, max_length=200)]


def password_policy(value):
    if value.casefold() in {'passwordpassword', '123456789012345', '12345678901234567890',
                             'estudolocal2026!', 'administrador123', 'qwertyuiopasdfgh'}:
        raise ValueError('Escolhe uma palavra-passe que não seja comum nem a da demonstração.')
    return value


NewPassword = Annotated[str, StringConstraints(strip_whitespace=False, min_length=15, max_length=200), AfterValidator(password_policy)]


class Input(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class Login(Input):
    email: str = Field(min_length=3, max_length=200)
    password: Password


class ServiceInput(Input):
    name: str = Field(min_length=2, max_length=100)
    team: str = Field(min_length=2, max_length=100)
    description: str = Field(default='', max_length=1000)
    criticality: Literal['Alta', 'Média', 'Baixa'] = 'Alta'
    slo_availability: float = Field(default=99.9, gt=0, le=100, allow_inf_nan=False)
    slo_latency_ms: int = Field(default=500, ge=1, le=120000)
    slo_latency_percent: float = Field(default=95, gt=0, le=100, allow_inf_nan=False)
    dependencies: list[int] = Field(default_factory=list, max_length=50)


class IncidentInput(Input):
    service_id: int = Field(gt=0)
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    severity: Literal['P1', 'P2', 'P3', 'P4'] = 'P2'


class IncidentUpdate(Input):
    status: Literal['open', 'acknowledged', 'investigating', 'resolved', 'closed']
    note: str = Field(default='', max_length=5000)
    root_cause: str = Field(default='', max_length=5000)
    prevention: str = Field(default='', max_length=5000)
    runbook: str = Field(default='', max_length=5000)


class Assignment(Input):
    user_id: int = Field(gt=0)


class Comment(Input):
    note: str = Field(min_length=1, max_length=5000)


class KnowledgeUse(Input):
    source_incident_id: int = Field(strict=True, gt=0, le=9223372036854775807)
    reason: str = Field(min_length=10, max_length=2000)


class Scenario(Input):
    service_id: int = Field(gt=0)
    kind: Literal['outage', 'latency', 'recovery']


class LabFault(Input):
    target: Literal['portal-lab', 'api-lab']
    kind: Literal['outage', 'latency', 'recovery']


class MonitoringInput(Input):
    url: str = Field(min_length=8, max_length=2048)
    enabled: bool = True


class UserDetails(Input):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    role: Literal['admin', 'operator', 'viewer'] = 'viewer'

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
            raise ValueError('Indica um endereço de email válido.')
        return value.lower()


class UserCreate(UserDetails):
    password: NewPassword


class UserUpdate(UserDetails):
    active: bool = True


class PasswordChange(Input):
    current_password: Password
    new_password: NewPassword


class AlertRuleInput(Input):
    enabled: bool = True
    outage_enabled: bool = True
    latency_enabled: bool = True
    failure_samples: int = Field(default=2, ge=2, le=5)
    recovery_samples: int = Field(default=2, ge=2, le=5)
    latency_ms: int | None = Field(default=None, ge=1, le=120000)
    outage_severity: Literal['P1', 'P2'] = 'P1'
    latency_severity: Literal['P2', 'P3', 'P4'] = 'P2'
    escalation_enabled: bool = False
    acknowledge_seconds: int = Field(default=900, ge=15, le=86400)
