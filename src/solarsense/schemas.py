from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1]
    device_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$")
    station_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9-]+$")
    boot_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    sequence: int = Field(ge=0, le=2**53)
    observed_at: datetime
    voltage_v: float | None
    current_a: float | None
    ac_power_w: float | None
    irradiance_wm2: float | None
    ambient_temp_c: float | None
    surface_temp_c: float | None
    humidity_pct: float | None
    light_adc: int | None = Field(ge=0, le=4095)
    load_limit_w: float | None = Field(gt=0, le=4000)
    relay_on: bool
    source_kind: Literal["simulated", "hardware"]
    simulator_version: Literal["1.0.0"]
    scenario_run_id: str = Field(min_length=1, max_length=64)
    clock_kind: Literal["event", "gateway_receive"]
    missing_reason: str | None = Field(default=None, max_length=160)
    dc_power_w: float | None = None
    light_lux: float | None = None
    hardware_protocol: Literal["espnow_gateway", "serial_data", "nano_json"] | None = None

    @field_validator("observed_at")
    @classmethod
    def utc_timestamp(cls, value):
        if value.tzinfo is None:
            raise ValueError("observed_at needs a UTC offset")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def missing_values(self):
        sensors = [
            self.voltage_v,
            self.current_a,
            self.ac_power_w,
            self.irradiance_wm2,
            self.ambient_temp_c,
            self.surface_temp_c,
            self.humidity_pct,
            self.light_adc,
        ]
        if self.source_kind == "hardware" and self.hardware_protocol is None:
            raise ValueError("Hardware readings require their protocol")
        if any(v is None for v in sensors) and not self.missing_reason:
            raise ValueError("Missing measurements need missing_reason")
        return self


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readings: list[Reading] = Field(min_length=1, max_length=50)


class ManualValues(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    voltage_v: float = Field(ge=0, le=80)
    current_a: float = Field(ge=0, le=30)
    ambient_temp_c: float = Field(ge=-30, le=70)
    surface_temp_c: float = Field(ge=-30, le=120)
    humidity_pct: float = Field(ge=0, le=100)
    light_adc: int = Field(ge=0, le=4095)
    irradiance_wm2: float = Field(ge=0, le=1500)
    ac_power_w: float = Field(ge=0, le=4000)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fault: Literal[
        "normal",
        "open_circuit",
        "short_circuit",
        "partial_shading",
        "soiling",
        "inverter_fault",
        "sensor_stuck",
        "sensor_offset",
        "missing",
        "unknown",
    ] = "normal"
    severity: float = Field(default=0.7, ge=0, le=1)
    network: Literal["normal", "disconnect", "delay", "duplicate"] = "normal"
    cloud: float = Field(default=1, ge=0.1, le=1.2)
    enabled: bool = True
    manual: ManualValues | None = None


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relay_on: bool
    ttl_seconds: int = Field(default=30, ge=5, le=120)


class Acknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relay_on: bool


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Literal[
        "normal",
        "open_circuit",
        "short_circuit",
        "partial_shading",
        "soiling",
        "inverter_fault",
        "unknown",
        "insufficient_evidence",
    ]
    reason: str = Field(min_length=5, max_length=500)
