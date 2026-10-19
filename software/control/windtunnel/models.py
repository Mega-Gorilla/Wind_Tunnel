from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Step(StrictModel):
    pwm_percent: float = Field(ge=0, le=100)
    settle_s: float = Field(ge=0, le=120)
    record_s: float = Field(ge=1, le=120)

    @field_validator("pwm_percent")
    @classmethod
    def starting_range(cls, value):
        if 0 < value < 20:
            raise ValueError("PWM must be 0 or 20–100 percent")
        return value


class Recipe(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["pwm"] = "pwm"
    steps: list[Step] = Field(min_length=1, max_length=12)
    repeat: int = Field(default=1, ge=1, le=5, strict=True)

    @property
    def duration_s(self):
        return sum(s.settle_s + s.record_s for s in self.steps) * self.repeat

    @model_validator(mode="after")
    def bounded_duration(self):
        if self.duration_s > 300:
            raise ValueError("Total run duration must not exceed 300 seconds")
        return self


class StartRequest(StrictModel):
    recipe: Recipe
    control_epoch: int = Field(ge=0, strict=True)
    remote_permit_id: str | None = Field(default=None, max_length=64)


class PermitRequest(StrictModel):
    max_pwm_percent: int = Field(default=100, ge=20, le=100, strict=True)


def canonical_ip(value: str) -> str:
    parsed = ip_address(value)
    if getattr(parsed, "scope_id", None):
        raise ValueError("Scoped IPv6 addresses are not supported")
    return str(getattr(parsed, "ipv4_mapped", None) or parsed)


class ClientRequest(StrictModel):
    name: str = Field(min_length=1, max_length=60)
    allowed_ips: list[str] = Field(min_length=1, max_length=8)
    scopes: list[Literal["read", "plan", "control", "stop"]] = Field(min_length=1, max_length=4)

    @field_validator("allowed_ips")
    @classmethod
    def exact_addresses(cls, values):
        return sorted(set(canonical_ip(v) for v in values))


class BootstrapRequest(StrictModel):
    code: str = Field(min_length=20, max_length=128)


class FaultRequest(StrictModel):
    fault: Literal["none", "offline", "sensor", "power"]
