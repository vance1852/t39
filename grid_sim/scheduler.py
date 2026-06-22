from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple, Callable
from .models import (
    SimState, Action, ActionType, LineStatus, SwitchStatus,
    PriorityLevel, Generator, Load, Line, FaultEvent,
)
from .network import NetworkAnalyzer, PowerFlowCalculator


class DispatchingStrategy:
    def __init__(self, name: str):
        self.name = name

    def select_alternatives(
        self, alternatives: List[Dict], state: SimState
    ) -> List[Dict]:
        raise NotImplementedError


class GreedyStrategy(DispatchingStrategy):
    def __init__(self):
        super().__init__("greedy")

    def select_alternatives(
        self, alternatives: List[Dict], state: SimState
    ) -> List[Dict]:
        sorted_alts = sorted(
            alternatives,
            key=lambda x: (
                -x.get("capacity", 0),
                x.get("length", 999),
            )
        )
        return sorted_alts


class ConservativeStrategy(DispatchingStrategy):
    def __init__(self, safety_margin: float = 0.8):
        super().__init__("conservative")
        self.safety_margin = safety_margin

    def select_alternatives(
        self, alternatives: List[Dict], state: SimState
    ) -> List[Dict]:
        filtered = [
            alt for alt in alternatives
            if alt.get("capacity", 0) >= self.safety_margin
        ]
        sorted_alts = sorted(
            filtered,
            key=lambda x: (
                -x.get("capacity", 0),
                x.get("length", 999),
            )
        )
        return sorted_alts if sorted_alts else sorted(
            alternatives, key=lambda x: -x.get("capacity", 0)
        )


class ShortestPathStrategy(DispatchingStrategy):
    def __init__(self):
        super().__init__("shortest_path")

    def select_alternatives(
        self, alternatives: List[Dict], state: SimState
    ) -> List[Dict]:
        sorted_alts = sorted(
            alternatives,
            key=lambda x: (
                x.get("length", 999),
                -x.get("capacity", 0),
            )
        )
        return sorted_alts


class Scheduler:
    def __init__(
        self,
        network_analyzer: NetworkAnalyzer,
        flow_calculator: PowerFlowCalculator,
        source_buses: Set[str],
        strategy: DispatchingStrategy = GreedyStrategy(),
    ):
        self.analyzer = network_analyzer
        self.flow_calc = flow_calculator
        self.source_buses = source_buses
        self.strategy = strategy

    def _add_action(
        self, state: SimState, time: float, action_type: ActionType,
        target_id: str, value: Optional[float] = None,
        reason: str = "", priority: int = 0
    ):
        action = Action(
            time=time,
            action_type=action_type,
            target_id=target_id,
            value=value,
            reason=reason,
            priority=priority,
        )
        state.actions.append(action)
        return action

    def process_faults(
        self, state: SimState, faults: List[FaultEvent],
        current_time: float
    ) -> List[str]:
        triggered = []
        for fault in faults:
            if abs(fault.time_hour - current_time) < 0.01 and \
               fault.id not in state.active_faults:
                state.active_faults.append(fault.id)
                triggered.append(fault.id)

                if fault.line_id:
                    line = state.lines.get(fault.line_id)
                    if line:
                        line.status = LineStatus.FAULTED
                        self._add_action(
                            state, current_time,
                            ActionType.FAULT_ISOLATE,
                            fault.line_id,
                            reason=f"线路故障: {fault.name}"
                        )
                        self.isolate_fault(state, fault.line_id, current_time)

                if fault.generator_id:
                    gen = state.generators.get(fault.generator_id)
                    if gen:
                        gen.is_online = False
                        gen.current_output = 0.0
                        gen.is_starting = False
                        gen.start_timer = 0.0
                        self._add_action(
                            state, current_time,
                            ActionType.GEN_STOP,
                            fault.generator_id,
                            reason=f"机组故障: {fault.name}"
                        )

        return triggered

    def isolate_fault(self, state: SimState, line_id: str, current_time: float):
        line = state.lines.get(line_id)
        if not line:
            return

        faulted_buses = {line.from_bus, line.to_bus}

        for lid, l in state.lines.items():
            if l.status == LineStatus.FAULTED:
                faulted_buses.add(l.from_bus)
                faulted_buses.add(l.to_bus)

        for lid, l in state.lines.items():
            if l.status != LineStatus.NORMAL:
                continue
            if l.from_bus in faulted_buses or l.to_bus in faulted_buses:
                if l.is_tie_switch or l.switch_status == SwitchStatus.OPEN:
                    continue

                switchable = False
                if l.from_bus in faulted_buses and l.to_bus not in faulted_buses:
                    switchable = True
                elif l.to_bus in faulted_buses and l.from_bus not in faulted_buses:
                    switchable = True

                if switchable:
                    l.switch_status = SwitchStatus.OPEN
                    l.status = LineStatus.ISOLATED
                    self._add_action(
                        state, current_time,
                        ActionType.SWITCH_OPEN,
                        lid,
                        reason=f"故障隔离: 断开{l.name}"
                    )

    def update_generator_states(self, state: SimState, dt: float):
        for gen_id, gen in state.generators.items():
            if gen.is_starting:
                gen.start_timer += dt
                if gen.start_timer >= gen.cold_start_time:
                    gen.is_starting = False
                    gen.is_online = True
                    gen.current_output = gen.min_output
                    self._add_action(
                        state, state.time,
                        ActionType.GEN_START,
                        gen_id,
                        value=gen.min_output,
                        reason=f"机组{gen.name}启动完成，并网运行"
                    )

    def dispatch_generation(
        self, state: SimState, dt: float,
        target_deficit: float, source_buses_in_component: Set[str]
    ) -> float:
        total_added = 0.0
        gens_by_priority = sorted(
            [
                (gen_id, gen) for gen_id, gen in state.generators.items()
                if gen.is_online and gen.bus_id in source_buses_in_component
            ],
            key=lambda x: (x[1].priority, -x[1].max_capacity)
        )

        for gen_id, gen in gens_by_priority:
            if total_added >= target_deficit - 0.01:
                break

            available_ramp = gen.available_ramp_up(dt)
            if available_ramp > 0.1:
                needed = target_deficit - total_added
                ramp_amount = min(available_ramp, needed)
                if ramp_amount > 0.1:
                    old_output = gen.current_output
                    gen.current_output += ramp_amount
                    total_added += ramp_amount
                    self._add_action(
                        state, state.time,
                        ActionType.GEN_RAMP,
                        gen_id,
                        value=gen.current_output,
                        reason=f"机组{gen.name}增出力: {old_output:.1f}→{gen.current_output:.1f}MW"
                    )

        if total_added < target_deficit - 0.1:
            for gen_id, gen in state.generators.items():
                if not gen.is_online and not gen.is_starting and \
                   gen.bus_id in source_buses_in_component:
                    needed = target_deficit - total_added
                    if gen.max_capacity > 0 and gen.max_capacity >= needed * 0.5:
                        gen.is_starting = True
                        gen.start_timer = 0.0
                        self._add_action(
                            state, state.time,
                            ActionType.GEN_START,
                            gen_id,
                            reason=f"启动备用机组{gen.name}(冷启动需{gen.cold_start_time}h)"
                        )

        return total_added

    def find_and_execute_transfer(
        self, state: SimState, isolated_buses: Set[str],
        transfer_target: float
    ) -> bool:
        tie_lines = {
            lid for lid, l in state.lines.items()
            if l.is_tie_switch and l.switch_status == SwitchStatus.OPEN
            and l.status == LineStatus.NORMAL
        }

        alternatives = self.analyzer.find_supply_alternatives(
            isolated_buses, state, self.source_buses, tie_lines
        )

        sorted_alts = self.strategy.select_alternatives(alternatives, state)

        for alt in sorted_alts:
            cap = alt.get("capacity", 0)
            if cap < transfer_target * 0.8:
                continue

            tie_id = alt.get("tie_line")
            if tie_id:
                line = state.lines[tie_id]
                line.switch_status = SwitchStatus.CLOSED
                path_desc = "联络线转供"
                if alt.get("source") and alt.get("target"):
                    path_desc = f"{alt['source']}→{alt['target']}"

                self._add_action(
                    state, state.time,
                    ActionType.SWITCH_CLOSE,
                    tie_id,
                    value=cap,
                    reason=f"转供{path_desc}, 容量{cap:.1f}MVA, 策略:{self.strategy.name}"
                )
                return True

        return False

    def shed_load_by_priority(
        self, state: SimState, deficit: float, component_buses: Set[str]
    ) -> float:
        if deficit <= 0.1:
            return 0.0

        total_shed = 0.0
        loads_in_comp = [
            (lid, load) for lid, load in state.loads.items()
            if load.bus_id in component_buses and not load.is_shed
        ]

        for priority_level in [PriorityLevel.LOW, PriorityLevel.MEDIUM,
                               PriorityLevel.HIGH, PriorityLevel.CRITICAL]:
            if total_shed >= deficit - 0.01:
                break

            level_loads = [
                (lid, load) for lid, load in loads_in_comp
                if load.priority == priority_level
            ]

            for lid, load in level_loads:
                if total_shed >= deficit - 0.01:
                    break

                load_demand = load.get_load_at_hour(int(state.time))
                if load_demand > 0.1:
                    load.is_shed = True
                    load.current_served = 0.0
                    total_shed += load_demand
                    self._add_action(
                        state, state.time,
                        ActionType.LOAD_SHED,
                        lid,
                        value=load_demand,
                        reason=f"限电: {load.name}, 优先级{priority_level.name}, 切除{load_demand:.1f}MW"
                    )

        return total_shed

    def restore_load_by_priority(
        self, state: SimState, surplus: float, component_buses: Set[str]
    ) -> float:
        if surplus <= 0.1:
            return 0.0

        total_restored = 0.0
        shed_loads = [
            (lid, load) for lid, load in state.loads.items()
            if load.bus_id in component_buses and load.is_shed
        ]

        for priority_level in [PriorityLevel.CRITICAL, PriorityLevel.HIGH,
                               PriorityLevel.MEDIUM, PriorityLevel.LOW]:
            if total_restored >= surplus - 0.01:
                break

            level_loads = [
                (lid, load) for lid, load in shed_loads
                if load.priority == priority_level
            ]

            for lid, load in level_loads:
                if total_restored >= surplus - 0.01:
                    break

                load_demand = load.get_load_at_hour(int(state.time))
                if load_demand > 0.1 and load_demand <= surplus - total_restored + 0.1:
                    load.is_shed = False
                    load.current_served = load_demand
                    total_restored += load_demand
                    self._add_action(
                        state, state.time,
                        ActionType.LOAD_RESTORE,
                        lid,
                        value=load_demand,
                        reason=f"恢复供电: {load.name}, 优先级{priority_level.name}, 恢复{load_demand:.1f}MW"
                    )

        return total_restored

    def check_secondary_faults(
        self, state: SimState, overloads: List[Tuple[str, bool]],
        current_time: float, overload_probability: float = 0.3
    ) -> int:
        secondary_count = 0
        for line_id, will_fail in overloads:
            if will_fail:
                line = state.lines[line_id]
                line.status = LineStatus.FAULTED
                line.has_secondary_fault = True
                state.secondary_faults += 1
                secondary_count += 1
                self._add_action(
                    state, current_time,
                    ActionType.SECONDARY_FAULT,
                    line_id,
                    reason=f"持续过载引发二次故障: {line.name}"
                )
                self.isolate_fault(state, line_id, current_time)
        return secondary_count

    def balance_component(
        self, state: SimState, component: Set[str], dt: float
    ) -> Tuple[float, float]:
        comp_sources = component & self.source_buses
        if not comp_sources:
            return (0.0, 0.0)

        total_gen = sum(
            gen.current_output for gen in state.generators.values()
            if gen.bus_id in component and gen.is_online
        )

        total_demand = sum(
            load.get_load_at_hour(int(state.time))
            for load in state.loads.values()
            if load.bus_id in component and not load.is_shed
        )

        balance = total_gen - total_demand

        total_shed = 0.0
        total_restored = 0.0

        if balance < -0.1:
            deficit = -balance

            added_gen = self.dispatch_generation(state, dt, deficit, comp_sources)
            deficit -= added_gen

            if deficit > 0.1:
                isolated = {b for b in component if b not in comp_sources}
                transferred = self.find_and_execute_transfer(
                    state, isolated, deficit
                )
                if transferred:
                    return (0, 0)

                if deficit > 0.1:
                    total_shed = self.shed_load_by_priority(
                        state, deficit, component
                    )

        elif balance > 0.1:
            surplus = balance
            total_restored = self.restore_load_by_priority(
                state, surplus, component
            )

        return (total_shed, total_restored)

    def step(
        self, state: SimState, dt: float,
        faults: List[FaultEvent],
        overload_probability: float = 0.3
    ) -> Dict:
        current_time = state.time

        triggered = self.process_faults(state, faults, current_time)

        self.update_generator_states(state, dt)

        self.flow_calc.calculate_simplified_flow(state, self.source_buses)

        components = self.analyzer.get_connected_components(state)

        total_shed = 0.0
        total_restored = 0.0
        for component in components:
            shed, restored = self.balance_component(state, component, dt)
            total_shed += shed
            total_restored += restored

        self.flow_calc.calculate_simplified_flow(state, self.source_buses)

        overloads = self.flow_calc.check_overloads(
            state, dt, overload_probability
        )

        secondary_count = self.check_secondary_faults(
            state, overloads, current_time, overload_probability
        )

        if secondary_count > 0:
            self.flow_calc.calculate_simplified_flow(state, self.source_buses)
            for component in self.analyzer.get_connected_components(state):
                self.balance_component(state, component, dt)

        return {
            "triggered_faults": triggered,
            "total_shed_mw": total_shed,
            "total_restored_mw": total_restored,
            "overloads": len(overloads),
            "secondary_faults": secondary_count,
        }
