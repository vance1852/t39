import pytest
from grid_sim.models import LineStatus, SwitchStatus


class TestNetworkConnectivity:
    def test_initial_graph_connected(self, network_analyzer, initial_state, source_buses):
        components = network_analyzer.get_connected_components(initial_state)
        assert len(components) >= 1
        energized = network_analyzer.get_energized_buses(initial_state, source_buses)
        assert "SRC1" in energized
        assert "SRC2" in energized

    def test_source_connection(self, network_analyzer, initial_state, source_buses):
        assert network_analyzer.is_connected_to_source("SRC1", initial_state, source_buses)
        assert network_analyzer.is_connected_to_source("SUB1", initial_state, source_buses)
        assert network_analyzer.is_connected_to_source("L1", initial_state, source_buses)

    def test_fault_isolation_disconnects_buses(self, network_analyzer, initial_state):
        initial_state.lines["LINE1"].status = LineStatus.FAULTED
        initial_state.lines["LINE1"].switch_status = SwitchStatus.OPEN

        components = network_analyzer.get_connected_components(initial_state)
        src1_component = None
        for comp in components:
            if "SRC1" in comp:
                src1_component = comp
                break
        assert src1_component is not None
        assert "SUB1" not in src1_component or len(components) > 1

    def test_tie_switch_closed_restores_connection(self, network_analyzer, initial_state):
        initial_state.lines["LINE1"].status = LineStatus.FAULTED
        initial_state.lines["LINE1"].switch_status = SwitchStatus.OPEN

        initial_state.lines["TIE3"].switch_status = SwitchStatus.CLOSED
        initial_state.lines["TIE3"].status = LineStatus.NORMAL

        src_buses = {"SRC1", "SRC2"}
        assert network_analyzer.is_connected_to_source("SUB2", initial_state, src_buses)

    def test_find_shortest_path(self, network_analyzer, initial_state):
        path = network_analyzer.find_shortest_path("SRC1", "L2", initial_state)
        assert path is not None
        assert len(path) >= 2

        line_ids = [edge[2]["line_id"] for edge in path]
        assert "LINE1" in line_ids or "LINE3" in line_ids

    def test_find_all_paths(self, network_analyzer, initial_state):
        paths = network_analyzer.find_all_paths("SRC1", "SUB2", initial_state, cutoff=5)
        assert len(paths) >= 1

    def test_path_capacity_calculation(self, network_analyzer, initial_state):
        path = network_analyzer.find_shortest_path("SRC1", "L1", initial_state)
        capacity = network_analyzer.get_path_capacity(path)
        assert capacity > 0
        assert capacity <= 50.0

    def test_minimum_cut(self, network_analyzer, initial_state):
        cut_value, cut_edges = network_analyzer.find_minimum_cut(
            "SRC1", "SUB1", initial_state
        )
        assert cut_value >= 0
        assert isinstance(cut_edges, list)
