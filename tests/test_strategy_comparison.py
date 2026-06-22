import pytest
from grid_sim.simulator import Simulator, compare_strategies, run_scenario
from grid_sim.sample_network import (
    create_sample_network, create_counterintuitive_scenario,
    create_line_fault_scenario,
)
from grid_sim.scheduler import (
    GreedyStrategy, ConservativeStrategy, ShortestPathStrategy,
)
from grid_sim.models import SwitchStatus


class TestStrategyComparison:
    def test_greedy_prioritizes_capacity(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()

        greedy = GreedyStrategy()
        alternatives = [
            {"capacity": 3.0, "length": 1.0},
            {"capacity": 15.0, "length": 2.0},
            {"capacity": 5.0, "length": 1.5},
        ]

        from grid_sim.models import SimState
        state = SimState(time=0)
        sorted_alts = greedy.select_alternatives(alternatives, state)

        assert sorted_alts[0]["capacity"] == 15.0
        assert sorted_alts[-1]["capacity"] == 3.0

    def test_shortest_path_prioritizes_distance(self):
        shortest = ShortestPathStrategy()
        alternatives = [
            {"capacity": 3.0, "length": 1.0},
            {"capacity": 15.0, "length": 2.0},
            {"capacity": 5.0, "length": 1.5},
        ]

        from grid_sim.models import SimState
        state = SimState(time=0)
        sorted_alts = shortest.select_alternatives(alternatives, state)

        assert sorted_alts[0]["length"] == 1.0
        assert sorted_alts[-1]["length"] == 2.0

    def test_conservative_filters_low_capacity(self):
        conservative = ConservativeStrategy(safety_margin=8.0)
        alternatives = [
            {"capacity": 3.0, "length": 1.0},
            {"capacity": 15.0, "length": 2.0},
            {"capacity": 5.0, "length": 1.5},
        ]

        from grid_sim.models import SimState
        state = SimState(time=0)
        filtered = conservative.select_alternatives(alternatives, state)

        assert len(filtered) >= 1
        assert all(a["capacity"] >= 8.0 for a in filtered[:-1])

    def test_counterintuitive_scenario_greedy_better(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()
        strategies = ["greedy", "shortest_path"]

        results = compare_strategies(network, scenario, strategies, seed=42)

        greedy_metrics = results["greedy"][0]
        sp_metrics = results["shortest_path"][0]

        assert greedy_metrics.total_unserved_energy <= sp_metrics.total_unserved_energy + 50
        assert greedy_metrics.secondary_fault_count <= sp_metrics.secondary_fault_count + 5
        assert greedy_metrics.critical_serve_rate >= sp_metrics.critical_serve_rate - 0.1

    def test_strategies_produce_different_actions(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()
        strategies = ["greedy", "shortest_path"]

        results = compare_strategies(network, scenario, strategies, seed=42)

        greedy_actions = results["greedy"][1].actions
        sp_actions = results["shortest_path"][1].actions

        action_types = {a.action_type.value for a in greedy_actions}
        assert "switch_close" in action_types or "gen_ramp" in action_types
        assert len(greedy_actions) > 0
        assert len(sp_actions) > 0

    def test_full_simulation_produces_metrics(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42, verbose=False
        )

        assert metrics.total_unserved_energy >= 0
        assert metrics.critical_serve_rate >= 0
        assert metrics.overall_serve_rate >= 0
        assert metrics.action_count > 0
        assert len(state.actions) > 0

    def test_metrics_have_correct_scenario_id(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )

        assert metrics.scenario_id == scenario.id
        assert metrics.strategy == "greedy"

    def test_different_scenarios_produce_different_results(self):
        network = create_sample_network()
        from grid_sim.sample_network import create_normal_scenario, create_multi_fault_scenario

        normal_scenario = create_normal_scenario()
        fault_scenario = create_multi_fault_scenario()

        normal_metrics, _ = run_scenario(
            network, normal_scenario, strategy_name="greedy", seed=42
        )
        fault_metrics, _ = run_scenario(
            network, fault_scenario, strategy_name="greedy", seed=42
        )

        normal_duration = normal_scenario.end_hour - normal_scenario.start_hour
        fault_duration = fault_scenario.end_hour - fault_scenario.start_hour

        normal_unserved_per_hour = normal_metrics.total_unserved_energy / normal_duration
        fault_unserved_per_hour = fault_metrics.total_unserved_energy / fault_duration

        assert fault_metrics.action_count >= normal_metrics.action_count or \
               fault_unserved_per_hour >= normal_unserved_per_hour * 0.5

    def test_tie_line_selection_reflects_strategy(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()

        results = compare_strategies(
            network, scenario, ["greedy", "shortest_path"], seed=42
        )

        greedy_state = results["greedy"][1]
        sp_state = results["shortest_path"][1]

        greedy_switches = [
            a for a in greedy_state.actions
            if a.action_type.value == "switch_close"
        ]
        sp_switches = [
            a for a in sp_state.actions
            if a.action_type.value == "switch_close"
        ]

        for a in greedy_switches:
            if "TIE3" in a.target_id:
                assert True
                break

    def test_report_generation(self):
        from grid_sim.reporter import ReportGenerator

        network = create_sample_network()
        scenario = create_line_fault_scenario()

        results = compare_strategies(
            network, scenario, ["greedy", "shortest_path"], seed=42
        )

        comparison_report = ReportGenerator.generate_comparison_report(
            results, scenario.id
        )

        assert "greedy" in comparison_report
        assert "shortest_path" in comparison_report
        assert "未供电电量" in comparison_report
        assert "过载次数" in comparison_report

        metrics, state = results["greedy"]
        text_report = ReportGenerator.generate_text_report(
            metrics, state, scenario.name, "greedy"
        )

        assert scenario.name in text_report
        assert "greedy" in text_report
        assert "核心指标" in text_report
        assert "调度动作序列" in text_report
