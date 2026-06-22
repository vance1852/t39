from __future__ import annotations
from typing import List, Dict, Set
from .models import (
    Bus, Generator, Load, Line, NetworkConfig,
    Scenario, FaultEvent, MaintenanceEvent,
    PriorityLevel, GeneratorType, SwitchStatus, LineStatus,
)


def create_sample_daily_curve() -> List[float]:
    return [
        0.5, 0.45, 0.42, 0.4, 0.42, 0.5,
        0.65, 0.8, 0.9, 0.95, 0.98, 1.0,
        0.98, 0.95, 0.9, 0.88, 0.92, 1.0,
        1.0, 0.95, 0.85, 0.75, 0.65, 0.55,
    ]


def create_sample_network() -> NetworkConfig:
    buses = [
        Bus(id="SRC1", name="主电源1", voltage=110.0, bus_type="source"),
        Bus(id="SRC2", name="备用电源2", voltage=110.0, bus_type="source"),
        Bus(id="SUB1", name="变电站1", voltage=35.0, bus_type="substation"),
        Bus(id="SUB2", name="变电站2", voltage=35.0, bus_type="substation"),
        Bus(id="SUB3", name="变电站3", voltage=10.0, bus_type="substation"),
        Bus(id="L1", name="工业负荷A", voltage=10.0, bus_type="load"),
        Bus(id="L2", name="医院负荷", voltage=10.0, bus_type="load"),
        Bus(id="L3", name="商业中心", voltage=10.0, bus_type="load"),
        Bus(id="L4", name="居民负荷B", voltage=10.0, bus_type="load"),
        Bus(id="L5", name="居民负荷C", voltage=10.0, bus_type="load"),
    ]

    generators = [
        Generator(
            id="GRID1", bus_id="SRC1", name="大电网1号",
            gen_type=GeneratorType.GRID, max_capacity=80.0,
            ramp_up_rate=30.0, ramp_down_rate=20.0,
            cold_start_time=0.0, priority=1,
        ),
        Generator(
            id="GRID2", bus_id="SRC2", name="大电网2号",
            gen_type=GeneratorType.GRID, max_capacity=60.0,
            ramp_up_rate=25.0, ramp_down_rate=15.0,
            cold_start_time=0.0, priority=2,
        ),
        Generator(
            id="DIESEL1", bus_id="SUB1", name="柴油发电机1号",
            gen_type=GeneratorType.DIESEL, max_capacity=15.0,
            ramp_up_rate=5.0, ramp_down_rate=8.0,
            cold_start_time=2.0, priority=5,
        ),
        Generator(
            id="GAS1", bus_id="SUB2", name="燃气轮机1号",
            gen_type=GeneratorType.GAS_TURBINE, max_capacity=20.0,
            ramp_up_rate=10.0, ramp_down_rate=12.0,
            cold_start_time=1.0, priority=3,
        ),
        Generator(
            id="ESS1", bus_id="SUB3", name="储能电站1号",
            gen_type=GeneratorType.ENERGY_STORAGE, max_capacity=10.0,
            ramp_up_rate=20.0, ramp_down_rate=20.0,
            cold_start_time=0.0, priority=4,
        ),
    ]

    daily_curve = create_sample_daily_curve()

    loads = [
        Load(
            id="LOAD1", bus_id="L1", name="工业负荷A",
            base_load=15.0, priority=PriorityLevel.HIGH,
            daily_curve=daily_curve,
        ),
        Load(
            id="LOAD2", bus_id="L2", name="医院负荷",
            base_load=8.0, priority=PriorityLevel.CRITICAL,
            daily_curve=daily_curve,
        ),
        Load(
            id="LOAD3", bus_id="L3", name="商业中心",
            base_load=12.0, priority=PriorityLevel.MEDIUM,
            daily_curve=daily_curve,
        ),
        Load(
            id="LOAD4", bus_id="L4", name="居民负荷B",
            base_load=10.0, priority=PriorityLevel.MEDIUM,
            daily_curve=daily_curve,
        ),
        Load(
            id="LOAD5", bus_id="L5", name="居民负荷C",
            base_load=8.0, priority=PriorityLevel.LOW,
            daily_curve=daily_curve,
        ),
    ]

    lines = [
        Line(
            id="LINE1", from_bus="SRC1", to_bus="SUB1",
            name="主线路1", max_capacity=50.0,
        ),
        Line(
            id="LINE2", from_bus="SRC2", to_bus="SUB2",
            name="主线路2", max_capacity=40.0,
        ),
        Line(
            id="LINE3", from_bus="SUB1", to_bus="SUB3",
            name="馈线3", max_capacity=25.0,
        ),
        Line(
            id="LINE4", from_bus="SUB2", to_bus="SUB3",
            name="馈线4", max_capacity=20.0,
        ),
        Line(
            id="LINE5", from_bus="SUB1", to_bus="L1",
            name="工业馈线", max_capacity=20.0,
        ),
        Line(
            id="LINE6", from_bus="SUB3", to_bus="L2",
            name="医院馈线", max_capacity=15.0,
        ),
        Line(
            id="LINE7", from_bus="SUB3", to_bus="L3",
            name="商业馈线", max_capacity=18.0,
        ),
        Line(
            id="LINE8", from_bus="SUB2", to_bus="L4",
            name="居民馈线B", max_capacity=15.0,
        ),
        Line(
            id="LINE9", from_bus="SUB1", to_bus="L5",
            name="居民馈线C", max_capacity=12.0,
        ),
        Line(
            id="TIE1", from_bus="SUB1", to_bus="SUB2",
            name="联络开关1", max_capacity=5.0,
            is_tie_switch=True, switch_status=SwitchStatus.OPEN,
            overload_threshold_time=1.5,
        ),
        Line(
            id="TIE2", from_bus="SUB2", to_bus="SUB3",
            name="联络开关2", max_capacity=3.0,
            is_tie_switch=True, switch_status=SwitchStatus.OPEN,
            overload_threshold_time=1.0,
        ),
        Line(
            id="TIE3", from_bus="SRC1", to_bus="SUB2",
            name="备用联络线", max_capacity=15.0,
            is_tie_switch=True, switch_status=SwitchStatus.OPEN,
            overload_threshold_time=2.0,
        ),
    ]

    return NetworkConfig(
        buses=buses,
        generators=generators,
        loads=loads,
        lines=lines,
        overload_secondary_fault_probability=0.4,
        overload_duration_trigger=1.0,
    )


def create_normal_scenario() -> Scenario:
    return Scenario(
        id="normal",
        name="正常运行",
        description="无故障，高峰时段正常运行",
        start_hour=0,
        end_hour=24,
        time_step=1.0,
        strategy="greedy",
    )


def create_peak_hour_scenario() -> Scenario:
    return Scenario(
        id="peak",
        name="高峰时段",
        description="晚高峰17-21点，大负荷运行",
        start_hour=16,
        end_hour=22,
        time_step=0.5,
        strategy="greedy",
    )


def create_line_fault_scenario() -> Scenario:
    faults = [
        FaultEvent(
            id="F1",
            name="主线路1故障",
            time_hour=19.0,
            line_id="LINE1",
            duration=3.0,
        ),
    ]
    return Scenario(
        id="line_fault",
        name="主线路故障",
        description="晚高峰主线路故障，需转供",
        faults=faults,
        start_hour=17,
        end_hour=23,
        time_step=0.5,
        strategy="greedy",
    )


def create_counterintuitive_scenario() -> Scenario:
    faults = [
        FaultEvent(
            id="F2",
            name="主线路2故障",
            time_hour=19.0,
            line_id="LINE2",
            duration=4.0,
        ),
    ]
    return Scenario(
        id="counterintuitive",
        name="反直觉转供场景",
        description="SUB2失电后，最短联络TIE2容量仅3MW不够，选择稍远的TIE3(15MW)更稳",
        faults=faults,
        start_hour=18,
        end_hour=24,
        time_step=0.5,
        strategy="greedy",
    )


def create_multi_fault_scenario() -> Scenario:
    faults = [
        FaultEvent(
            id="F3",
            name="GRID1机组跳闸",
            time_hour=18.0,
            generator_id="GRID1",
            duration=5.0,
        ),
        FaultEvent(
            id="F4",
            name="LINE3故障",
            time_hour=20.0,
            line_id="LINE3",
            duration=2.0,
        ),
    ]
    return Scenario(
        id="multi_fault",
        name="多重故障",
        description="机组跳闸后叠加线路故障，考验备用调度",
        faults=faults,
        start_hour=16,
        end_hour=24,
        time_step=0.5,
        strategy="greedy",
    )


def create_maintenance_scenario() -> Scenario:
    maintenance = [
        MaintenanceEvent(
            id="M1",
            name="主变检修",
            start_hour=10.0,
            end_hour=16.0,
            line_id="LINE1",
        ),
    ]
    return Scenario(
        id="maintenance",
        name="计划检修",
        description="主线路白天检修，晚高峰前恢复",
        maintenance=maintenance,
        start_hour=8,
        end_hour=20,
        time_step=1.0,
        strategy="greedy",
    )


def get_all_scenarios() -> Dict[str, Scenario]:
    return {
        "normal": create_normal_scenario(),
        "peak": create_peak_hour_scenario(),
        "line_fault": create_line_fault_scenario(),
        "counterintuitive": create_counterintuitive_scenario(),
        "multi_fault": create_multi_fault_scenario(),
        "maintenance": create_maintenance_scenario(),
    }


def get_counterintuitive_description() -> str:
    return """
反直觉场景说明：
- 主线路LINE2在晚高峰19:00故障，导致SUB2失电
- SUB2带L4居民负荷10MW(高峰系数1.0)
- 可选联络线：
  1. TIE2(SUB2→SUB3): 距离最短(直接连接)，但容量仅3MW，不足以转供10MW
  2. TIE3(SRC1→SUB2): 距离稍远(需经过SRC1)，但容量15MW，可完全转供
- 最短路径策略(TIE2)会导致过载甚至二次故障
- 容量优先策略(TIE3)虽然路径较长，但更稳定
"""
