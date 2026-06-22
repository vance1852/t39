from __future__ import annotations
import random
from typing import Dict, List, Optional, Set, Tuple, Callable
import copy
from .models import (
    NetworkConfig, Scenario, SimState, Metrics,
    Generator, Load, Line, FaultEvent,
    PriorityLevel, LineStatus, SwitchStatus,
)
from .network import NetworkAnalyzer, PowerFlowCalculator
from .scheduler import (
    Scheduler, GreedyStrategy, ConservativeStrategy,
    ShortestPathStrategy, DispatchingStrategy,
)


class Simulator:
    def __init__(
        self,
        network_config: NetworkConfig,
        scenario: Scenario,
        strategy: Optional[DispatchingStrategy] = None,
        seed: Optional[int] = None,
    ):
        self.config = network_config
        self.scenario = scenario
        self.seed = seed
        if seed is not None:
            random.seed(seed)

        self.analyzer = NetworkAnalyzer(network_config.buses, network_config.lines)
        self.flow_calc = PowerFlowCalculator(self.analyzer)

        self.source_buses = self._identify_source_buses()

        if strategy is None:
            strategy = self._create_strategy(scenario.strategy)
        self.strategy = strategy

        self.scheduler = Scheduler(
            self.analyzer, self.flow_calc, self.source_buses, strategy
        )

        self.state = self._initialize_state()

    def _identify_source_buses(self) -> Set[str]:
        source_buses = set()
        for gen in self.config.generators:
            source_buses.add(gen.bus_id)
        return source_buses

    def _create_strategy(self, strategy_name: str) -> DispatchingStrategy:
        strategies = {
            "greedy": GreedyStrategy(),
            "conservative": ConservativeStrategy(),
            "shortest_path": ShortestPathStrategy(),
        }
        return strategies.get(strategy_name, GreedyStrategy())

    def _initialize_state(self) -> SimState:
        state = SimState(time=self.scenario.start_hour)

        for gen in self.config.generators:
            gen_copy = gen.model_copy(deep=True)
            if gen_copy.gen_type.value == "grid":
                gen_copy.is_online = True
                gen_copy.current_output = gen_copy.min_output or 1.0
            state.generators[gen.id] = gen_copy

        for load in self.config.loads:
            load_copy = load.model_copy(deep=True)
            state.loads[load.id] = load_copy
            state.total_load_served[load.id] = 0.0
            state.total_load_demand[load.id] = 0.0

        for line in self.config.lines:
            line_copy = line.model_copy(deep=True)
            state.lines[line.id] = line_copy

        return state

    def _apply_maintenance(self, current_time: float):
        for maint in self.scenario.maintenance:
            if maint.start_hour <= current_time < maint.end_hour:
                if maint.line_id:
                    line = self.state.lines.get(maint.line_id)
                    if line and line.status == LineStatus.NORMAL:
                        line.status = LineStatus.ISOLATED
                        line.switch_status = SwitchStatus.OPEN
            elif current_time >= maint.end_hour:
                if maint.line_id:
                    line = self.state.lines.get(maint.line_id)
                    if line and line.status == LineStatus.ISOLATED:
                        line.status = LineStatus.NORMAL
                        line.switch_status = SwitchStatus.CLOSED

    def _accumulate_metrics(self, dt: float):
        for load_id, load in self.state.loads.items():
            demand = load.get_load_at_hour(int(self.state.time))
            served = load.current_served if not load.is_shed else 0.0

            self.state.total_load_demand[load_id] += demand * dt
            self.state.total_load_served[load_id] += served * dt

            if served < demand - 0.01:
                unserved = (demand - served) * dt
                self.state.unserved_energy += unserved
                if load.priority == PriorityLevel.CRITICAL:
                    self.state.critical_unserved += unserved
                elif load.priority == PriorityLevel.HIGH:
                    self.state.high_unserved += unserved

    def _compute_final_metrics(self) -> Metrics:
        metrics = Metrics(
            scenario_id=self.scenario.id,
            strategy=self.strategy.name,
            overload_count=self.state.overload_events,
            secondary_fault_count=self.state.secondary_faults,
            action_count=len(self.state.actions),
        )

        metrics.total_unserved_energy = round(self.state.unserved_energy, 2)

        total_demand = sum(self.state.total_load_demand.values())
        total_served = sum(self.state.total_load_served.values())
        if total_demand > 0:
            metrics.overall_serve_rate = round(total_served / total_demand, 4)

        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH,
                         PriorityLevel.MEDIUM, PriorityLevel.LOW]:
            level_demand = sum(
                self.state.total_load_demand[lid]
                for lid, l in self.state.loads.items()
                if l.priority == priority
            )
            level_served = sum(
                self.state.total_load_served[lid]
                for lid, l in self.state.loads.items()
                if l.priority == priority
            )
            if level_demand > 0:
                rate = round(level_served / level_demand, 4)
                if priority == PriorityLevel.CRITICAL:
                    metrics.critical_serve_rate = rate
                elif priority == PriorityLevel.HIGH:
                    metrics.high_serve_rate = rate
                elif priority == PriorityLevel.MEDIUM:
                    metrics.medium_serve_rate = rate
                else:
                    metrics.low_serve_rate = rate

        from .models import ActionType
        for action in self.state.actions:
            if action.action_type == ActionType.GEN_START:
                metrics.gen_start_count += 1
            elif action.action_type == ActionType.LOAD_SHED:
                metrics.load_shed_count += 1
            elif action.action_type in [ActionType.SWITCH_OPEN, ActionType.SWITCH_CLOSE]:
                metrics.switch_operations += 1

        return metrics

    def run(self, verbose: bool = False) -> Metrics:
        dt = self.scenario.time_step
        current_time = self.scenario.start_hour

        if verbose:
            print(f"\n=== 开始模拟: {self.scenario.name} ===")
            print(f"时间范围: {current_time}h - {self.scenario.end_hour}h")
            print(f"时间步长: {dt}h")
            print(f"调度策略: {self.strategy.name}")

        while current_time < self.scenario.end_hour:
            self.state.time = current_time

            self._apply_maintenance(current_time)

            step_result = self.scheduler.step(
                self.state, dt,
                self.scenario.faults,
                self.config.overload_secondary_fault_probability,
            )

            self._accumulate_metrics(dt)

            if verbose:
                self._print_step_info(current_time, step_result)

            current_time += dt

        if verbose:
            print(f"\n=== 模拟完成 ===")

        return self._compute_final_metrics()

    def _print_step_info(self, time: float, result: Dict):
        gen_output = sum(
            g.current_output for g in self.state.generators.values()
            if g.is_online
        )
        total_demand = sum(
            l.get_load_at_hour(int(time)) for l in self.state.loads.values()
            if not l.is_shed
        )
        print(f"\n[时间 {time:5.1f}h] "
              f"发电={gen_output:5.1f}MW "
              f"需求={total_demand:5.1f}MW "
              f"未供电={self.state.unserved_energy:5.1f}MWh "
              f"过载={result['overloads']} "
              f"二次故障={result['secondary_faults']}")


def run_scenario(
    network_config: NetworkConfig,
    scenario: Scenario,
    strategy_name: str = "greedy",
    seed: Optional[int] = None,
    verbose: bool = False,
) -> Tuple[Metrics, SimState]:
    sim = Simulator(network_config, scenario, seed=seed)
    sim.strategy = sim._create_strategy(strategy_name)
    sim.scheduler.strategy = sim.strategy
    metrics = sim.run(verbose=verbose)
    return metrics, sim.state


def compare_strategies(
    network_config: NetworkConfig,
    scenario: Scenario,
    strategies: List[str],
    seed: Optional[int] = None,
) -> Dict[str, Tuple[Metrics, SimState]]:
    results = {}
    base_seed = seed if seed is not None else 42

    for strategy_name in strategies:
        sim = Simulator(
            network_config, scenario,
            seed=base_seed,
        )
        sim.strategy = sim._create_strategy(strategy_name)
        sim.scheduler.strategy = sim.strategy
        metrics = sim.run(verbose=False)
        results[strategy_name] = (metrics, sim.state)

    return results
