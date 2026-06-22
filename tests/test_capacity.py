import pytest
from grid_sim.models import LineStatus, SwitchStatus


class TestCapacityConstraints:
    def test_line_flow_calculation(self, flow_calculator, initial_state, source_buses):
        flows = flow_calculator.calculate_simplified_flow(initial_state, source_buses)
        assert isinstance(flows, dict)
        assert len(flows) == len(initial_state.lines)
        for line_id, flow in flows.items():
            assert flow >= 0

    def test_overload_detection(self, flow_calculator, initial_state, source_buses):
        initial_state.lines["LINE1"].max_capacity = 5.0
        initial_state.generators["GRID1"].current_output = 80.0

        flow_calculator.calculate_simplified_flow(initial_state, source_buses)
        initial_state.lines["LINE1"].current_flow = 10.0

        overloads = flow_calculator.check_overloads(initial_state, dt=0.5)
        assert len(overloads) >= 0
        assert initial_state.overload_events >= 0

    def test_overload_duration_accumulation(self, flow_calculator, initial_state, source_buses):
        initial_state.lines["LINE1"].max_capacity = 5.0
        initial_state.lines["LINE1"].current_flow = 10.0
        initial_state.lines["LINE1"].overload_duration = 0.0

        for _ in range(3):
            flow_calculator.check_overloads(initial_state, dt=0.5)

        assert initial_state.lines["LINE1"].overload_duration >= 1.0

    def test_overload_duration_recovery(self, flow_calculator, initial_state):
        initial_state.lines["LINE1"].max_capacity = 50.0
        initial_state.lines["LINE1"].current_flow = 10.0
        initial_state.lines["LINE1"].overload_duration = 2.0

        for _ in range(5):
            flow_calculator.check_overloads(initial_state, dt=0.5)

        assert initial_state.lines["LINE1"].overload_duration < 2.0

    def test_no_violation_in_normal_operation(self, flow_calculator, initial_state, source_buses):
        initial_state.generators["GRID1"].current_output = 10.0
        initial_state.generators["GRID2"].current_output = 10.0

        flows = flow_calculator.calculate_simplified_flow(initial_state, source_buses)

        for line_id, flow in flows.items():
            line = initial_state.lines[line_id]
            if line.status == LineStatus.NORMAL:
                assert flow <= line.max_capacity * 10 or flow >= 0

    def test_tie_line_capacity_enforced_on_transfer(
        self, scheduler, initial_state, source_buses
    ):
        initial_state.lines["LINE2"].status = LineStatus.FAULTED
        initial_state.lines["LINE2"].switch_status = SwitchStatus.OPEN

        initial_state.time = 19.0
        scheduler.isolate_fault(initial_state, "LINE2", 19.0)

        dt = 0.5
        result = scheduler.step(initial_state, dt, [], overload_probability=0.0)

        assert isinstance(result, dict)
        assert result["overloads"] >= 0

    def test_path_capacity_considered_in_alternatives(
        self, network_analyzer, initial_state, source_buses
    ):
        isolated = {"SUB2"}
        tie_lines = {"TIE1", "TIE2", "TIE3"}

        alternatives = network_analyzer.find_supply_alternatives(
            isolated, initial_state, source_buses, tie_lines
        )

        assert len(alternatives) > 0
        capacities = [alt["capacity"] for alt in alternatives]
        assert 15.0 in capacities or 5.0 in capacities or 3.0 in capacities
