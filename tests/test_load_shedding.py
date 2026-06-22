import pytest
from grid_sim.models import PriorityLevel, LineStatus, SwitchStatus, ActionType


class TestLoadSheddingPriority:
    def test_low_priority_shed_first(self, scheduler, initial_state):
        component = {"SRC1", "SUB1", "L1", "L5"}
        deficit = 5.0
        initial_state.time = 19.0

        initial_state.loads["LOAD1"].priority = PriorityLevel.HIGH
        initial_state.loads["LOAD5"].priority = PriorityLevel.LOW
        initial_state.loads["LOAD1"].is_shed = False
        initial_state.loads["LOAD5"].is_shed = False

        shed = scheduler.shed_load_by_priority(initial_state, deficit, component)

        assert shed >= 0
        assert initial_state.loads["LOAD5"].is_shed
        assert not initial_state.loads["LOAD1"].is_shed

    def test_critical_load_shed_last(self, scheduler, initial_state):
        component = {"SRC1", "SUB3", "L2", "L3", "L4"}
        deficit = 100.0

        initial_state.loads["LOAD2"].priority = PriorityLevel.CRITICAL
        initial_state.loads["LOAD3"].priority = PriorityLevel.MEDIUM
        initial_state.loads["LOAD4"].priority = PriorityLevel.MEDIUM

        for lid in ["LOAD2", "LOAD3", "LOAD4"]:
            initial_state.loads[lid].is_shed = False

        shed = scheduler.shed_load_by_priority(initial_state, deficit, component)

        assert shed > 0
        assert initial_state.loads["LOAD3"].is_shed
        assert initial_state.loads["LOAD4"].is_shed

        med_shed = initial_state.loads["LOAD3"].is_shed or initial_state.loads["LOAD4"].is_shed
        crit_not_shed = not initial_state.loads["LOAD2"].is_shed or (
            initial_state.loads["LOAD3"].is_shed and initial_state.loads["LOAD4"].is_shed
        )
        assert crit_not_shed

    def test_load_restore_priority_order(self, scheduler, initial_state):
        component = {"SRC1", "SUB3", "L2", "L3"}
        surplus = 20.0

        initial_state.loads["LOAD2"].priority = PriorityLevel.CRITICAL
        initial_state.loads["LOAD3"].priority = PriorityLevel.MEDIUM
        initial_state.loads["LOAD2"].is_shed = True
        initial_state.loads["LOAD3"].is_shed = True

        actions_before = len(initial_state.actions)
        restored = scheduler.restore_load_by_priority(initial_state, surplus, component)

        restore_actions = [
            a for a in initial_state.actions[actions_before:]
            if a.action_type == ActionType.LOAD_RESTORE
        ]

        assert restored > 0
        if len(restore_actions) >= 2:
            assert restore_actions[0].target_id == "LOAD2"
            assert restore_actions[1].target_id == "LOAD3"

    def test_action_recorded_for_shedding(self, scheduler, initial_state):
        component = {"SRC1", "L5"}
        deficit = 8.0

        actions_before = len(initial_state.actions)
        shed = scheduler.shed_load_by_priority(initial_state, deficit, component)

        shed_actions = [
            a for a in initial_state.actions[actions_before:]
            if a.action_type == ActionType.LOAD_SHED
        ]

        assert len(shed_actions) >= 1
        assert shed_actions[0].target_id == "LOAD5"
        assert shed_actions[0].value is not None
        assert "LOW" in shed_actions[0].reason

    def test_no_shed_when_sufficient_generation(
        self, scheduler, initial_state, source_buses
    ):
        initial_state.generators["GRID1"].current_output = 100.0
        initial_state.generators["GRID1"].is_online = True
        initial_state.generators["GRID2"].current_output = 60.0
        initial_state.generators["GRID2"].is_online = True

        dt = 1.0
        initial_state.time = 12.0

        components = scheduler.analyzer.get_connected_components(initial_state)
        for component in components:
            shed, restored = scheduler.balance_component(initial_state, component, dt)
            assert shed == 0.0

        for load in initial_state.loads.values():
            assert not load.is_shed

    def test_shed_amount_matches_deficit(self, scheduler, initial_state):
        component = {"SRC1", "L1", "L5"}
        deficit = 15.0
        initial_state.time = 19.0

        initial_state.loads["LOAD1"].is_shed = False
        initial_state.loads["LOAD5"].is_shed = False

        shed = scheduler.shed_load_by_priority(initial_state, deficit, component)

        total_available = (
            initial_state.loads["LOAD1"].get_load_at_hour(19) +
            initial_state.loads["LOAD5"].get_load_at_hour(19)
        )

        assert shed >= min(deficit * 0.9, total_available)
        assert shed <= deficit + 10.0

    def test_metrics_track_unserved_energy(self, initial_state, source_buses):
        from grid_sim.simulator import Simulator
        from grid_sim.sample_network import create_normal_scenario

        network = type('obj', (object,), {
            'buses': [], 'generators': list(initial_state.generators.values()),
            'loads': list(initial_state.loads.values()),
            'lines': list(initial_state.lines.values()),
            'overload_secondary_fault_probability': 0.0,
        })()

        scenario = create_normal_scenario()
        scenario.end_hour = scenario.start_hour + 1.0
        scenario.time_step = 1.0

        for gid, gen in initial_state.generators.items():
            gen.current_output = 0.0
            gen.is_online = False

        initial_state.time = scenario.start_hour

        sim = Simulator.__new__(Simulator)
        sim.config = network
        sim.scenario = scenario
        sim.state = initial_state
        sim.source_buses = source_buses

        sim._accumulate_metrics(dt=1.0)

        assert initial_state.unserved_energy > 0
        assert initial_state.high_unserved > 0 or initial_state.medium_unserved > 0
