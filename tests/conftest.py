import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from grid_sim.sample_network import create_sample_network, get_all_scenarios
from grid_sim.models import SimState
from grid_sim.network import NetworkAnalyzer, PowerFlowCalculator
from grid_sim.scheduler import Scheduler, GreedyStrategy


@pytest.fixture
def sample_network():
    return create_sample_network()


@pytest.fixture
def sample_scenarios():
    return get_all_scenarios()


@pytest.fixture
def source_buses(sample_network):
    return {gen.bus_id for gen in sample_network.generators}


@pytest.fixture
def network_analyzer(sample_network):
    return NetworkAnalyzer(sample_network.buses, sample_network.lines)


@pytest.fixture
def flow_calculator(network_analyzer):
    return PowerFlowCalculator(network_analyzer)


@pytest.fixture
def initial_state(sample_network, source_buses):
    state = SimState(time=0.0)
    for gen in sample_network.generators:
        gen_copy = gen.model_copy(deep=True)
        if gen_copy.gen_type.value == "grid":
            gen_copy.is_online = True
            gen_copy.current_output = 10.0
        state.generators[gen.id] = gen_copy
    for load in sample_network.loads:
        load_copy = load.model_copy(deep=True)
        state.loads[load.id] = load_copy
        state.total_load_served[load.id] = 0.0
        state.total_load_demand[load.id] = 0.0
    for line in sample_network.lines:
        line_copy = line.model_copy(deep=True)
        state.lines[line.id] = line_copy
    return state


@pytest.fixture
def scheduler(network_analyzer, flow_calculator, source_buses):
    return Scheduler(
        network_analyzer, flow_calculator, source_buses,
        strategy=GreedyStrategy()
    )
