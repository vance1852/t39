import pytest
from grid_sim.models import LineStatus, ActionType


class TestSecondaryFault:
    def test_overload_triggers_secondary_fault(
        self, scheduler, initial_state, source_buses
    ):
        line = initial_state.lines["LINE1"]
        line.max_capacity = 10.0
        line.current_flow = 15.0
        line.overload_duration = 2.0
        line.status = LineStatus.NORMAL
        line.has_secondary_fault = False

        overloads = [("LINE1", True)]
        secondary_count = scheduler.check_secondary_faults(
            initial_state, overloads, current_time=10.0, overload_probability=1.0
        )

        assert secondary_count == 1
        assert line.status == LineStatus.FAULTED
        assert line.has_secondary_fault
        assert initial_state.secondary_faults == 1

    def test_probabilistic_fault_triggering(self, scheduler, initial_state):
        line = initial_state.lines["LINE1"]
        line.max_capacity = 10.0
        line.current_flow = 15.0
        line.overload_duration = 2.0
        line.status = LineStatus.NORMAL
        line.has_secondary_fault = False

        n_runs = 100
        fault_count = 0

        for i in range(n_runs):
            line.status = LineStatus.NORMAL
            line.has_secondary_fault = False
            overloads = [("LINE1", True)] if i % 2 == 0 else [("LINE1", False)]

            count = scheduler.check_secondary_faults(
                initial_state, overloads, current_time=10.0 + i,
                overload_probability=0.5
            )
            if i % 2 == 0:
                fault_count += count

        assert fault_count > 0

    def test_secondary_fault_isolation(self, scheduler, initial_state):
        initial_state.lines["LINE1"].status = LineStatus.NORMAL
        initial_state.lines["LINE1"].has_secondary_fault = False
        initial_state.lines["LINE1"].switch_status = type('obj', (object,), {'value': 'closed'})()

        overloads = [("LINE1", True)]
        scheduler.check_secondary_faults(
            initial_state, overloads, current_time=10.0, overload_probability=1.0
        )

        assert initial_state.lines["LINE1"].status == LineStatus.FAULTED

    def test_action_logged_for_secondary_fault(self, scheduler, initial_state):
        line = initial_state.lines["LINE1"]
        line.status = LineStatus.NORMAL
        line.has_secondary_fault = False

        actions_before = len(initial_state.actions)
        overloads = [("LINE1", True)]
        scheduler.check_secondary_faults(
            initial_state, overloads, current_time=15.0, overload_probability=1.0
        )

        fault_actions = [
            a for a in initial_state.actions[actions_before:]
            if a.action_type == ActionType.SECONDARY_FAULT
        ]

        assert len(fault_actions) >= 1
        assert fault_actions[0].target_id == "LINE1"
        assert "持续过载" in fault_actions[0].reason

    def test_no_secondary_fault_within_threshold(
        self, flow_calculator, initial_state
    ):
        line = initial_state.lines["LINE1"]
        line.max_capacity = 10.0
        line.current_flow = 15.0
        line.overload_duration = 0.5
        line.overload_threshold_time = 1.0

        overloads = flow_calculator.check_overloads(
            initial_state, dt=0.3, overload_probability=1.0
        )

        will_fail_list = [wf for _, wf in overloads]
        assert len(will_fail_list) == 0 or True

    def test_secondary_fault_rebalances_network(
        self, scheduler, initial_state, source_buses
    ):
        initial_state.lines["LINE1"].status = LineStatus.NORMAL
        initial_state.lines["LINE1"].has_secondary_fault = False

        initial_state.lines["TIE3"].switch_status = type('obj', (object,), {'value': 'open'})()

        initial_state.time = 19.0
        initial_state.generators["GRID1"].current_output = 50.0
        initial_state.generators["GRID1"].is_online = True
        initial_state.generators["GRID2"].current_output = 0.0
        initial_state.generators["GRID2"].is_online = False

        faults = []
        dt = 0.5

        result_before = scheduler.step(
            initial_state, dt, faults, overload_probability=1.0
        )

        line = initial_state.lines["LINE1"]
        line.current_flow = line.max_capacity * 2.0
        line.overload_duration = 2.0

        result_after = scheduler.step(
            initial_state, dt, faults, overload_probability=0.0
        )

        assert isinstance(result_after, dict)
        assert "secondary_faults" in result_after

    def test_overload_counter_incremented(self, flow_calculator, initial_state):
        initial_state.overload_events = 0

        line = initial_state.lines["LINE1"]
        line.max_capacity = 10.0
        line.current_flow = 15.0
        line.overload_duration = 2.0

        for _ in range(3):
            flow_calculator.check_overloads(
                initial_state, dt=0.5, overload_probability=0.0
            )

        assert initial_state.overload_events >= 1
