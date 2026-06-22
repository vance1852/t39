from __future__ import annotations
import networkx as nx
from typing import Dict, List, Optional, Set, Tuple, Callable
from .models import (
    Bus, Generator, Load, Line, SimState,
    LineStatus, SwitchStatus, PriorityLevel,
)


class NetworkAnalyzer:
    def __init__(self, buses: List[Bus], lines: List[Line]):
        self.buses = {b.id: b for b in buses}
        self.lines = {l.id: l for l in lines}

    def build_graph(self, state: SimState) -> nx.Graph:
        G = nx.Graph()
        for bus_id in self.buses:
            G.add_node(bus_id)
        for line_id, line in self.lines.items():
            current_line = state.lines[line_id]
            if current_line.status == LineStatus.NORMAL and \
               current_line.switch_status == SwitchStatus.CLOSED:
                G.add_edge(
                    line.from_bus, line.to_bus,
                    line_id=line_id,
                    capacity=current_line.max_capacity,
                    weight=1.0 / max(current_line.max_capacity, 0.1),
                )
        return G

    def get_connected_components(self, state: SimState) -> List[Set[str]]:
        G = self.build_graph(state)
        return list(nx.connected_components(G))

    def is_connected_to_source(
        self, bus_id: str, state: SimState, source_buses: Set[str]
    ) -> bool:
        G = self.build_graph(state)
        if bus_id not in G:
            return False
        for src in source_buses:
            if src in G and nx.has_path(G, bus_id, src):
                return True
        return False

    def get_energized_buses(self, state: SimState, source_buses: Set[str]) -> Set[str]:
        G = self.build_graph(state)
        energized = set()
        for src in source_buses:
            if src in G:
                try:
                    reachable = nx.node_connected_component(G, src)
                    energized.update(reachable)
                except nx.NetworkXError:
                    pass
        return energized

    def find_shortest_path(
        self, from_bus: str, to_bus: str, state: SimState,
        weight: str = "weight"
    ) -> Optional[List[Tuple[str, str, Dict]]]:
        G = self.build_graph(state)
        if from_bus not in G or to_bus not in G:
            return None
        if not nx.has_path(G, from_bus, to_bus):
            return None
        try:
            path_nodes = nx.shortest_path(G, from_bus, to_bus, weight=weight)
            edges = []
            for i in range(len(path_nodes) - 1):
                u, v = path_nodes[i], path_nodes[i + 1]
                edge_data = G.get_edge_data(u, v)
                edges.append((u, v, edge_data))
            return edges
        except nx.NetworkXError:
            return None

    def find_all_paths(
        self, from_bus: str, to_bus: str, state: SimState,
        cutoff: int = 10
    ) -> List[List[Tuple[str, str, Dict]]]:
        G = self.build_graph(state)
        if from_bus not in G or to_bus not in G:
            return []
        paths = []
        try:
            for path_nodes in nx.all_simple_paths(G, from_bus, to_bus, cutoff=cutoff):
                edges = []
                for i in range(len(path_nodes) - 1):
                    u, v = path_nodes[i], path_nodes[i + 1]
                    edge_data = G.get_edge_data(u, v)
                    edges.append((u, v, edge_data))
                paths.append(edges)
        except nx.NetworkXError:
            pass
        return paths

    def find_minimum_cut(
        self, source_bus: str, target_bus: str, state: SimState
    ) -> Tuple[float, List[str]]:
        G = self.build_graph(state)
        if source_bus not in G or target_bus not in G:
            return (0.0, [])
        try:
            cut_value, partition = nx.minimum_cut(
                G, source_bus, target_bus, capacity="capacity"
            )
            cut_edges = []
            reachable, non_reachable = partition
            for u, v, data in G.edges(data=True):
                if (u in reachable and v in non_reachable) or \
                   (v in reachable and u in non_reachable):
                    cut_edges.append(data["line_id"])
            return cut_value, cut_edges
        except nx.NetworkXError:
            return (0.0, [])

    def get_path_capacity(self, path: List[Tuple[str, str, Dict]]) -> float:
        if not path:
            return 0.0
        return min(edge[2].get("capacity", 0.0) for edge in path)

    def get_path_length(self, path: List[Tuple[str, str, Dict]]) -> float:
        return sum(edge[2].get("weight", 1.0) for edge in path)

    def find_supply_alternatives(
        self, isolated_buses: Set[str], state: SimState,
        source_buses: Set[str], tie_line_ids: Optional[Set[str]] = None
    ) -> List[Dict]:
        alternatives = []
        for isolated in isolated_buses:
            for src in source_buses:
                if tie_line_ids:
                    for tie_id in tie_line_ids:
                        line = state.lines[tie_id]
                        if line.from_bus == src and line.to_bus in isolated_buses:
                            alternatives.append({
                                "source": src,
                                "target": line.to_bus,
                                "tie_line": tie_id,
                                "path": [(line.from_bus, line.to_bus, {
                                    "line_id": tie_id,
                                    "capacity": line.max_capacity,
                                })],
                                "capacity": line.max_capacity,
                            })
                        elif line.to_bus == src and line.from_bus in isolated_buses:
                            alternatives.append({
                                "source": src,
                                "target": line.from_bus,
                                "tie_line": tie_id,
                                "path": [(line.from_bus, line.to_bus, {
                                    "line_id": tie_id,
                                    "capacity": line.max_capacity,
                                })],
                                "capacity": line.max_capacity,
                            })
                else:
                    paths = self.find_all_paths(src, isolated, state, cutoff=6)
                    for path in paths:
                        alternatives.append({
                            "source": src,
                            "target": isolated,
                            "path": path,
                            "capacity": self.get_path_capacity(path),
                            "length": self.get_path_length(path),
                        })
        return alternatives


class PowerFlowCalculator:
    def __init__(self, network_analyzer: NetworkAnalyzer):
        self.analyzer = network_analyzer

    def calculate_simplified_flow(
        self, state: SimState, source_buses: Set[str]
    ) -> Dict[str, float]:
        line_flows: Dict[str, float] = {}
        for line_id in state.lines:
            line_flows[line_id] = 0.0

        G = self.analyzer.build_graph(state)
        components = list(nx.connected_components(G))

        for component in components:
            comp_sources = component & source_buses
            if not comp_sources:
                continue

            total_generation = sum(
                state.generators[gen_id].current_output
                for gen_id, gen in state.generators.items()
                if gen.bus_id in component and gen.is_online
            )

            total_demand = sum(
                load.get_load_at_hour(int(state.time))
                for load_id, load in state.loads.items()
                if load.bus_id in component and not load.is_shed
            )

            if total_demand <= 0:
                continue

            served_ratio = min(1.0, total_generation / total_demand) if total_demand > 0 else 1.0

            for load_id, load in state.loads.items():
                if load.bus_id in component and not load.is_shed:
                    load.current_served = load.get_load_at_hour(int(state.time)) * served_ratio

            for gen_id, gen in state.generators.items():
                if gen.bus_id in component and gen.is_online:
                    actual_output = min(gen.current_output, total_demand)
                    gen.current_output = actual_output

            for line_id, line in state.lines.items():
                if line.status != LineStatus.NORMAL:
                    continue
                if line.from_bus not in component or line.to_bus not in component:
                    continue

                from_gen = sum(
                    g.current_output
                    for g in state.generators.values()
                    if g.bus_id == line.from_bus and g.is_online
                )
                from_load = sum(
                    l.current_served
                    for l in state.loads.values()
                    if l.bus_id == line.from_bus and not l.is_shed
                )
                net_injection = from_gen - from_load

                try:
                    degree = G.degree(line.from_bus)
                    if degree > 1:
                        line_flows[line_id] = abs(net_injection) / degree
                    else:
                        line_flows[line_id] = abs(net_injection)
                except Exception:
                    line_flows[line_id] = 0.0

        for line_id, flow in line_flows.items():
            state.lines[line_id].current_flow = flow

        return line_flows

    def check_overloads(
        self, state: SimState, dt: float,
        overload_probability: float = 0.3
    ) -> List[Tuple[str, bool]]:
        overloads = []
        for line_id, line in state.lines.items():
            if line.status != LineStatus.NORMAL or line.has_secondary_fault:
                continue

            if line.current_flow > line.max_capacity:
                line.overload_duration += dt
                if line.overload_duration > line.overload_threshold_time:
                    import random
                    will_fail = random.random() < overload_probability
                    overloads.append((line_id, will_fail))
                    state.overload_events += 1
            else:
                line.overload_duration = max(0, line.overload_duration - dt * 0.5)

        return overloads
