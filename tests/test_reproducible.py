import pytest
import csv
import json
import tempfile
import os
from pathlib import Path
from grid_sim.simulator import run_scenario, compare_strategies
from grid_sim.sample_network import (
    create_sample_network, create_line_fault_scenario,
    create_counterintuitive_scenario,
)
from grid_sim.reporter import ReportGenerator
from grid_sim.models import ActionType


class TestActionLogReproducibility:
    def test_same_seed_produces_same_actions(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()
        seed = 42

        metrics1, state1 = run_scenario(
            network, scenario, strategy_name="greedy", seed=seed
        )
        metrics2, state2 = run_scenario(
            network, scenario, strategy_name="greedy", seed=seed
        )

        assert len(state1.actions) == len(state2.actions)

        for a1, a2 in zip(state1.actions, state2.actions):
            assert a1.time == a2.time
            assert a1.action_type == a2.action_type
            assert a1.target_id == a2.target_id
            assert a1.value == a2.value
            assert a1.reason == a2.reason

    def test_different_seeds_may_produce_different_actions(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()

        metrics1, state1 = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )
        metrics2, state2 = run_scenario(
            network, scenario, strategy_name="greedy", seed=123
        )

        assert metrics1.total_unserved_energy >= 0
        assert metrics2.total_unserved_energy >= 0

    def test_action_log_export_csv(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig') as f:
            temp_path = f.name

        try:
            ReportGenerator.export_actions_csv(state, temp_path)

            assert os.path.exists(temp_path)

            with open(temp_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) >= 2
            assert rows[0] == [
                "时间(h)", "动作类型", "目标ID", "数值", "原因", "优先级"
            ]

            assert len(rows) - 1 == len(state.actions)

            for i, row in enumerate(rows[1:]):
                action = state.actions[i]
                assert float(row[0]) == action.time
                assert row[1] == action.action_type.value
                assert row[2] == action.target_id
        finally:
            os.unlink(temp_path)

    def test_metrics_export_csv(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        results = compare_strategies(
            network, scenario, ["greedy", "shortest_path"], seed=42
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig') as f:
            temp_path = f.name

        try:
            ReportGenerator.export_metrics_csv(results, temp_path)

            assert os.path.exists(temp_path)

            with open(temp_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) >= 3
            assert "策略" in rows[0]
            assert "未供电MWh" in rows[0]
        finally:
            os.unlink(temp_path)

    def test_state_export_json(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            temp_path = f.name

        try:
            ReportGenerator.export_state_json(state, temp_path)

            assert os.path.exists(temp_path)

            with open(temp_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert "unserved_energy" in data
            assert "generators" in data
            assert "loads" in data
            assert "actions" in data
            assert len(data["actions"]) == len(state.actions)

            for i, action_data in enumerate(data["actions"]):
                action = state.actions[i]
                assert action_data["time"] == action.time
                assert action_data["type"] == action.action_type.value
                assert action_data["target_id"] == action.target_id
        finally:
            os.unlink(temp_path)

    def test_action_sequence_timestamps_monotonic(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )

        timestamps = [a.time for a in state.actions]
        assert timestamps == sorted(timestamps)

    def test_batch_comparison_reproducible(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()
        strategies = ["greedy", "conservative", "shortest_path"]
        seed = 99

        results1 = compare_strategies(network, scenario, strategies, seed=seed)
        results2 = compare_strategies(network, scenario, strategies, seed=seed)

        for strategy in strategies:
            m1, s1 = results1[strategy]
            m2, s2 = results2[strategy]

            assert m1.total_unserved_energy == m2.total_unserved_energy
            assert m1.secondary_fault_count == m2.secondary_fault_count
            assert m1.action_count == m2.action_count
            assert len(s1.actions) == len(s2.actions)

    def test_import_export_roundtrip(self):
        network = create_sample_network()
        scenario = create_line_fault_scenario()

        metrics, state = run_scenario(
            network, scenario, strategy_name="greedy", seed=42
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "actions.csv")
            json_path = os.path.join(tmpdir, "state.json")

            ReportGenerator.export_actions_csv(state, csv_path)
            ReportGenerator.export_state_json(state, json_path)

            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                csv_rows = list(reader)

            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            assert len(csv_rows) - 1 == len(json_data["actions"])

            for i in range(len(json_data["actions"])):
                csv_time = float(csv_rows[i + 1][0])
                json_time = json_data["actions"][i]["time"]
                assert abs(csv_time - json_time) < 0.001

    def test_action_formatting(self):
        from grid_sim.reporter import ReportGenerator
        from grid_sim.models import Action

        action = Action(
            time=19.5,
            action_type=ActionType.LOAD_SHED,
            target_id="LOAD5",
            value=8.0,
            reason="限电测试",
        )

        formatted = ReportGenerator.format_action(action)
        assert "19.5" in formatted
        assert "LOAD5" in formatted
        assert "8.0" in formatted
        assert "限电测试" in formatted

    def test_deterministic_fault_processing(self):
        network = create_sample_network()
        scenario = create_counterintuitive_scenario()
        seed = 7

        for _ in range(3):
            metrics, state = run_scenario(
                network, scenario, strategy_name="greedy", seed=seed
            )
            fault_actions = [
                a for a in state.actions
                if a.action_type in [ActionType.FAULT_ISOLATE, ActionType.SECONDARY_FAULT]
            ]
            assert len(fault_actions) >= 1
            assert fault_actions[0].time == 19.0
