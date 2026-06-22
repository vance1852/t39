from __future__ import annotations
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import timedelta


class PriorityLevel(int, Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class GeneratorType(str, Enum):
    GRID = "grid"
    DIESEL = "diesel"
    GAS_TURBINE = "gas_turbine"
    ENERGY_STORAGE = "energy_storage"


class SwitchStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class LineStatus(str, Enum):
    NORMAL = "normal"
    FAULTED = "faulted"
    ISOLATED = "isolated"


class Bus(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    name: str
    voltage: float = Field(..., description="kV")
    bus_type: str = Field(default="load", description="source/substation/load")


class Load(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    bus_id: str
    name: str
    base_load: float = Field(..., description="MW")
    priority: PriorityLevel = PriorityLevel.MEDIUM
    daily_curve: List[float] = Field(..., description="24小时负荷系数")
    is_shed: bool = False
    current_served: float = 0.0

    def get_load_at_hour(self, hour: int) -> float:
        idx = hour % len(self.daily_curve)
        return self.base_load * self.daily_curve[idx]


class Generator(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    bus_id: str
    name: str
    gen_type: GeneratorType = GeneratorType.GRID
    max_capacity: float = Field(..., description="MW")
    min_output: float = 0.0
    current_output: float = 0.0
    is_online: bool = False
    ramp_up_rate: float = Field(..., description="MW/hour")
    ramp_down_rate: float = Field(..., description="MW/hour")
    cold_start_time: float = Field(default=0, description="小时")
    start_timer: float = 0.0
    is_starting: bool = False
    priority: int = 10

    def available_ramp_up(self, dt_hours: float) -> float:
        if not self.is_online:
            return 0.0
        max_ramp = self.ramp_up_rate * dt_hours
        return min(max_ramp, self.max_capacity - self.current_output)

    def available_ramp_down(self, dt_hours: float) -> float:
        if not self.is_online:
            return 0.0
        max_ramp = self.ramp_down_rate * dt_hours
        return min(max_ramp, self.current_output - self.min_output)


class Line(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    from_bus: str
    to_bus: str
    name: str
    max_capacity: float = Field(..., description="MVA")
    status: LineStatus = LineStatus.NORMAL
    current_flow: float = 0.0
    overload_duration: float = 0.0
    overload_threshold_time: float = Field(default=1.0, description="小时")
    has_secondary_fault: bool = False
    is_tie_switch: bool = False
    switch_status: SwitchStatus = SwitchStatus.CLOSED
    reactance: float = 0.1


class FaultEvent(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    name: str
    time_hour: float
    line_id: Optional[str] = None
    generator_id: Optional[str] = None
    bus_id: Optional[str] = None
    duration: float = Field(default=float("inf"), description="小时，inf为永久性故障")


class MaintenanceEvent(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    name: str
    start_hour: float
    end_hour: float
    line_id: Optional[str] = None
    generator_id: Optional[str] = None


class Scenario(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str
    name: str
    description: str
    faults: List[FaultEvent] = Field(default_factory=list)
    maintenance: List[MaintenanceEvent] = Field(default_factory=list)
    strategy: str = "greedy"
    start_hour: float = 0.0
    end_hour: float = 24.0
    time_step: float = 1.0


class ActionType(str, Enum):
    GEN_START = "gen_start"
    GEN_STOP = "gen_stop"
    GEN_RAMP = "gen_ramp"
    SWITCH_OPEN = "switch_open"
    SWITCH_CLOSE = "switch_close"
    LOAD_SHED = "load_shed"
    LOAD_RESTORE = "load_restore"
    FAULT_ISOLATE = "fault_isolate"
    SECONDARY_FAULT = "secondary_fault"


class Action(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    time: float
    action_type: ActionType
    target_id: str
    value: Optional[float] = None
    reason: str = ""
    priority: int = 0


class SimState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    time: float
    generators: Dict[str, Generator] = Field(default_factory=dict)
    loads: Dict[str, Load] = Field(default_factory=dict)
    lines: Dict[str, Line] = Field(default_factory=dict)
    active_faults: List[str] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)
    unserved_energy: float = 0.0
    critical_unserved: float = 0.0
    high_unserved: float = 0.0
    overload_events: int = 0
    secondary_faults: int = 0
    total_load_served: Dict[str, float] = Field(default_factory=dict)
    total_load_demand: Dict[str, float] = Field(default_factory=dict)


class Metrics(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    scenario_id: str
    strategy: str
    total_unserved_energy: float = 0.0
    critical_serve_rate: float = 0.0
    high_serve_rate: float = 0.0
    medium_serve_rate: float = 0.0
    low_serve_rate: float = 0.0
    overall_serve_rate: float = 0.0
    overload_count: int = 0
    secondary_fault_count: int = 0
    action_count: int = 0
    gen_start_count: int = 0
    load_shed_count: int = 0
    switch_operations: int = 0
    peak_shaving_mwh: float = 0.0


class NetworkConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    buses: List[Bus] = Field(default_factory=list)
    generators: List[Generator] = Field(default_factory=list)
    loads: List[Load] = Field(default_factory=list)
    lines: List[Line] = Field(default_factory=list)
    base_frequency: float = 50.0
    overload_secondary_fault_probability: float = 0.3
    overload_duration_trigger: float = 1.0
