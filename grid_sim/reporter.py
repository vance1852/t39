from __future__ import annotations
import json
import csv
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from .models import Metrics, SimState, Action, ActionType
from .simulator import Simulator


class ReportGenerator:
    @staticmethod
    def format_action(action: Action) -> str:
        value_str = f"={action.value:.1f}" if action.value is not None else ""
        return (
            f"[{action.time:5.1f}h] {action.action_type.value:15s} "
            f"{action.target_id:10s}{value_str:10s} | {action.reason}"
        )

    @staticmethod
    def generate_text_report(
        metrics: Metrics, state: SimState,
        scenario_name: str, strategy_name: str,
        include_actions: bool = True,
        max_actions: int = 100,
    ) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append(f"配电网保供策略模拟报告")
        lines.append("=" * 80)
        lines.append(f"场景: {scenario_name}")
        lines.append(f"策略: {strategy_name}")
        lines.append("")

        lines.append("-" * 80)
        lines.append("核心指标")
        lines.append("-" * 80)
        lines.append(f"  总未供电电量:      {metrics.total_unserved_energy:8.2f} MWh")
        lines.append(f"  重要负荷保障率:    {metrics.critical_serve_rate:8.1%}")
        lines.append(f"  高压负荷保障率:    {metrics.high_serve_rate:8.1%}")
        lines.append(f"  中压负荷保障率:    {metrics.medium_serve_rate:8.1%}")
        lines.append(f"  低压负荷保障率:    {metrics.low_serve_rate:8.1%}")
        lines.append(f"  综合供电保障率:    {metrics.overall_serve_rate:8.1%}")
        lines.append("")
        lines.append(f"  过载次数:          {metrics.overload_count:8d} 次")
        lines.append(f"  二次故障次数:      {metrics.secondary_fault_count:8d} 次")
        lines.append(f"  机组启动次数:      {metrics.gen_start_count:8d} 次")
        lines.append(f"  限电操作次数:      {metrics.load_shed_count:8d} 次")
        lines.append(f"  开关操作次数:      {metrics.switch_operations:8d} 次")
        lines.append(f"  总调度动作数:      {metrics.action_count:8d} 次")
        lines.append("")

        lines.append("-" * 80)
        lines.append("各负荷供电情况")
        lines.append("-" * 80)
        lines.append(f"  {'负荷ID':12s} {'名称':12s} {'优先级':8s} {'需求(MWh)':10s} {'供电(MWh)':10s} {'保障率':8s}")
        for load_id, load in sorted(state.loads.items()):
            demand = state.total_load_demand.get(load_id, 0)
            served = state.total_load_served.get(load_id, 0)
            rate = served / demand if demand > 0 else 1.0
            lines.append(
                f"  {load_id:12s} {load.name:12s} {load.priority.name:8s} "
                f"{demand:10.2f} {served:10.2f} {rate:8.1%}"
            )
        lines.append("")

        if include_actions and state.actions:
            lines.append("-" * 80)
            lines.append("调度动作序列")
            lines.append("-" * 80)
            display_actions = state.actions[:max_actions]
            for action in display_actions:
                lines.append(f"  {ReportGenerator.format_action(action)}")
            if len(state.actions) > max_actions:
                lines.append(f"  ... 还有 {len(state.actions) - max_actions} 条动作记录")
            lines.append("")

        action_summary = ReportGenerator._summarize_actions(state.actions)
        lines.append("-" * 80)
        lines.append("动作类型统计")
        lines.append("-" * 80)
        for action_type, count in action_summary.items():
            lines.append(f"  {action_type:25s}: {count} 次")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _summarize_actions(actions: List[Action]) -> Dict[str, int]:
        summary = {}
        for action in actions:
            key = action.action_type.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    @staticmethod
    def generate_comparison_report(
        results: Dict[str, Tuple[Metrics, SimState]],
        scenario_name: str,
    ) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append(f"策略对比报告 - 场景: {scenario_name}")
        lines.append("=" * 80)
        lines.append("")

        strategy_names = list(results.keys())
        metrics_list = [results[s][0] for s in strategy_names]

        lines.append("-" * 80)
        lines.append("指标对比")
        lines.append("-" * 80)

        header = f"{'指标':25s}"
        for name in strategy_names:
            header += f" {name:>15s}"
        lines.append(header)

        metric_rows = [
            ("总未供电电量(MWh)", "total_unserved_energy", "f2"),
            ("重要负荷保障率(%)", "critical_serve_rate", "pct"),
            ("高压负荷保障率(%)", "high_serve_rate", "pct"),
            ("中压负荷保障率(%)", "medium_serve_rate", "pct"),
            ("低压负荷保障率(%)", "low_serve_rate", "pct"),
            ("综合保障率(%)", "overall_serve_rate", "pct"),
            ("过载次数", "overload_count", "d"),
            ("二次故障次数", "secondary_fault_count", "d"),
            ("机组启动次数", "gen_start_count", "d"),
            ("限电次数", "load_shed_count", "d"),
            ("开关操作次数", "switch_operations", "d"),
            ("总动作数", "action_count", "d"),
        ]

        for label, attr, fmt in metric_rows:
            row = f"{label:25s}"
            best_value = None
            best_idx = -1
            values = []

            for i, m in enumerate(metrics_list):
                val = getattr(m, attr)
                values.append(val)

                if "unserved" in attr or "count" in attr:
                    if best_value is None or val < best_value:
                        best_value = val
                        best_idx = i
                else:
                    if best_value is None or val > best_value:
                        best_value = val
                        best_idx = i

            for i, val in enumerate(values):
                if fmt == "f2":
                    val_str = f"{val:15.2f}"
                elif fmt == "pct":
                    val_str = f"{val*100:14.1f}%"
                else:
                    val_str = f"{val:15d}"

                if i == best_idx and len(metrics_list) > 1:
                    val_str = "*" + val_str[1:]
                row += val_str

            lines.append(row)

        lines.append("")
        lines.append("* 表示该指标下最优策略")
        lines.append("")

        lines.append("-" * 80)
        lines.append("推荐结论")
        lines.append("-" * 80)

        best_strategy = ReportGenerator._select_best_strategy(
            strategy_names, metrics_list
        )
        lines.append(f"  综合评估推荐策略: {best_strategy}")
        lines.append("")

        if "counterintuitive" in scenario_name:
            lines.append("  反直觉场景分析:")
            lines.append("    最短路径策略可能选择容量不足的联络线，导致过载和二次故障。")
            lines.append("    容量优先策略虽然路径较长，但能保障供电可靠性。")
            lines.append("    在高峰负荷下，充足的转供容量比路径长度更重要。")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _select_best_strategy(
        strategy_names: List[str], metrics_list: List[Metrics]
    ) -> str:
        scores = []
        for name, m in zip(strategy_names, metrics_list):
            score = 0.0
            score += m.critical_serve_rate * 100
            score += m.high_serve_rate * 50
            score += m.overall_serve_rate * 30
            score -= m.total_unserved_energy * 0.5
            score -= m.secondary_fault_count * 20
            score -= m.overload_count * 5
            scores.append((score, name))

        scores.sort(reverse=True)
        return scores[0][1]

    @staticmethod
    def export_actions_csv(
        state: SimState, output_path: str
    ):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "时间(h)", "动作类型", "目标ID", "数值", "原因", "优先级"
            ])
            for action in state.actions:
                writer.writerow([
                    action.time,
                    action.action_type.value,
                    action.target_id,
                    action.value,
                    action.reason,
                    action.priority,
                ])

    @staticmethod
    def export_metrics_csv(
        results: Dict[str, Tuple[Metrics, SimState]],
        output_path: str,
    ):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "策略", "场景", "未供电MWh", "重要保障率%", "高压保障率%",
                "中压保障率%", "低压保障率%", "综合保障率%",
                "过载次数", "二次故障", "机组启动", "限电次数", "开关操作", "总动作数"
            ])
            for strategy_name, (metrics, state) in results.items():
                writer.writerow([
                    strategy_name,
                    metrics.scenario_id,
                    f"{metrics.total_unserved_energy:.2f}",
                    f"{metrics.critical_serve_rate*100:.1f}",
                    f"{metrics.high_serve_rate*100:.1f}",
                    f"{metrics.medium_serve_rate*100:.1f}",
                    f"{metrics.low_serve_rate*100:.1f}",
                    f"{metrics.overall_serve_rate*100:.1f}",
                    metrics.overload_count,
                    metrics.secondary_fault_count,
                    metrics.gen_start_count,
                    metrics.load_shed_count,
                    metrics.switch_operations,
                    metrics.action_count,
                ])

    @staticmethod
    def export_state_json(
        state: SimState, output_path: str
    ):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = {
            "final_time": state.time,
            "unserved_energy": state.unserved_energy,
            "critical_unserved": state.critical_unserved,
            "high_unserved": state.high_unserved,
            "overload_events": state.overload_events,
            "secondary_faults": state.secondary_faults,
            "generators": {
                gid: {
                    "name": g.name,
                    "is_online": g.is_online,
                    "current_output": g.current_output,
                    "max_capacity": g.max_capacity,
                }
                for gid, g in state.generators.items()
            },
            "loads": {
                lid: {
                    "name": l.name,
                    "priority": l.priority.name,
                    "is_shed": l.is_shed,
                    "total_demand": state.total_load_demand.get(lid, 0),
                    "total_served": state.total_load_served.get(lid, 0),
                }
                for lid, l in state.loads.items()
            },
            "lines": {
                lid: {
                    "name": l.name,
                    "status": l.status.value,
                    "max_capacity": l.max_capacity,
                    "has_secondary_fault": l.has_secondary_fault,
                }
                for lid, l in state.lines.items()
            },
            "actions": [
                {
                    "time": a.time,
                    "type": a.action_type.value,
                    "target_id": a.target_id,
                    "value": a.value,
                    "reason": a.reason,
                }
                for a in state.actions
            ],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
