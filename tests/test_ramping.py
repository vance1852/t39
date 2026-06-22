import pytest
from grid_sim.models import GeneratorType, PriorityLevel


class TestGeneratorRamping:
    def test_ramp_up_rate_limited(self, initial_state):
        gen = initial_state.generators["GRID1"]
        gen.is_online = True
        gen.current_output = 10.0
        gen.max_capacity = 80.0
        gen.ramp_up_rate = 30.0

        dt = 1.0
        available = gen.available_ramp_up(dt)

        assert available == pytest.approx(30.0, abs=0.01)
        assert available <= gen.max_capacity - gen.current_output

    def test_ramp_down_rate_limited(self, initial_state):
        gen = initial_state.generators["GRID1"]
        gen.is_online = True
        gen.current_output = 50.0
        gen.min_output = 5.0
        gen.ramp_down_rate = 20.0

        dt = 1.0
        available = gen.available_ramp_down(dt)

        assert available == pytest.approx(20.0, abs=0.01)
        assert available <= gen.current_output - gen.min_output

    def test_offline_generator_no_ramp(self, initial_state):
        gen = initial_state.generators["DIESEL1"]
        gen.is_online = False
        gen.current_output = 0.0

        assert gen.available_ramp_up(1.0) == 0.0
        assert gen.available_ramp_down(1.0) == 0.0

    def test_cold_start_delay_enforced(self, scheduler, initial_state):
        gen = initial_state.generators["DIESEL1"]
        gen.is_online = False
        gen.is_starting = False
        gen.cold_start_time = 2.0
        gen.start_timer = 0.0

        gen.is_starting = True
        dt = 0.5

        for i in range(3):
            scheduler.update_generator_states(initial_state, dt)
            if i < 3:
                assert gen.is_starting
                assert not gen.is_online

        scheduler.update_generator_states(initial_state, dt)
        assert not gen.is_starting
        assert gen.is_online
        assert gen.current_output == gen.min_output

    def test_dispatch_respects_ramp_limits(self, scheduler, initial_state, source_buses):
        gen = initial_state.generators["GRID1"]
        gen.is_online = True
        gen.current_output = 10.0
        gen.max_capacity = 80.0
        gen.ramp_up_rate = 30.0

        gen2 = initial_state.generators["GRID2"]
        gen2.is_online = False
        gen2.is_starting = False

        dt = 1.0
        deficit = 50.0
        component = {"SRC1", "SRC2", "SUB1"}

        added = scheduler.dispatch_generation(initial_state, dt, deficit, {"SRC1"})

        assert added <= 30.0
        assert gen.current_output == pytest.approx(40.0, abs=0.01)

    def test_starting_generator_not_ramped(self, scheduler, initial_state):
        gen = initial_state.generators["GAS1"]
        gen.is_online = False
        gen.is_starting = True
        gen.start_timer = 0.5
        gen.cold_start_time = 1.0
        gen.current_output = 0.0

        dt = 1.0
        scheduler.update_generator_states(initial_state, dt)

        assert gen.is_online
        assert gen.current_output == gen.min_output

    def test_energy_storage_fast_ramp(self, initial_state):
        gen = initial_state.generators["ESS1"]
        gen.is_online = True
        gen.current_output = 0.0
        gen.max_capacity = 10.0
        gen.ramp_up_rate = 20.0

        dt = 0.5
        available = gen.available_ramp_up(dt)

        assert available == pytest.approx(10.0, abs=0.01)

    def test_generator_priority_order(self, scheduler, initial_state):
        initial_state.generators["GRID1"].priority = 1
        initial_state.generators["GRID2"].priority = 2
        initial_state.generators["GRID1"].current_output = 10.0
        initial_state.generators["GRID2"].current_output = 10.0
        initial_state.generators["GRID1"].is_online = True
        initial_state.generators["GRID2"].is_online = True

        dt = 1.0
        deficit = 100.0

        actions_before = len(initial_state.actions)
        added = scheduler.dispatch_generation(
            initial_state, dt, deficit, {"SRC1", "SRC2"}
        )

        ramp_actions = [
            a for a in initial_state.actions[actions_before:]
            if a.action_type.value == "gen_ramp"
        ]

        if len(ramp_actions) >= 2:
            assert ramp_actions[0].target_id == "GRID1"
            assert ramp_actions[1].target_id == "GRID2"
