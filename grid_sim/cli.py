from __future__ import annotations
import click
import sys
from typing import List, Optional
from pathlib import Path
from .sample_network import (
    create_sample_network, get_all_scenarios,
    get_counterintuitive_description,
)
from .simulator import run_scenario, compare_strategies
from .reporter import ReportGenerator


@click.group()
@click.version_option()
def cli():
    """配电网保供策略模拟器 - CLI工具"""
    pass


@cli.command()
@click.option("--scenario", "-s", default="normal",
              help="场景名称: normal/peak/line_fault/counterintuitive/multi_fault/maintenance")
@click.option("--strategy", "-t", default="greedy",
              help="调度策略: greedy/conservative/shortest_path")
@click.option("--verbose", "-v", is_flag=True, help="显示详细运行过程")
@click.option("--seed", type=int, default=42, help="随机种子")
@click.option("--export-actions", type=click.Path(), help="导出动作日志CSV路径")
@click.option("--export-report", type=click.Path(), help="导出报告文本路径")
@click.option("--export-json", type=click.Path(), help="导出状态JSON路径")
def run(scenario: str, strategy: str, verbose: bool, seed: int,
        export_actions: Optional[str], export_report: Optional[str],
        export_json: Optional[str]):
    """运行单场景模拟"""
    network = create_sample_network()
    scenarios = get_all_scenarios()

    if scenario not in scenarios:
        click.echo(f"错误: 未知场景 '{scenario}'")
        click.echo(f"可用场景: {', '.join(scenarios.keys())}")
        sys.exit(1)

    if scenario == "counterintuitive":
        click.echo(get_counterintuitive_description())

    scn = scenarios[scenario]
    click.echo(f"正在模拟场景: {scn.name}")
    click.echo(f"描述: {scn.description}")
    click.echo(f"策略: {strategy}")

    metrics, state = run_scenario(
        network, scn, strategy_name=strategy,
        seed=seed, verbose=verbose
    )

    report = ReportGenerator.generate_text_report(
        metrics, state, scn.name, strategy
    )
    click.echo("\n" + report)

    if export_actions:
        ReportGenerator.export_actions_csv(state, export_actions)
        click.echo(f"动作日志已导出到: {export_actions}")

    if export_report:
        Path(export_report).parent.mkdir(parents=True, exist_ok=True)
        with open(export_report, "w", encoding="utf-8") as f:
            f.write(report)
        click.echo(f"报告已导出到: {export_report}")

    if export_json:
        ReportGenerator.export_state_json(state, export_json)
        click.echo(f"状态数据已导出到: {export_json}")


@cli.command()
@click.option("--scenario", "-s", default="counterintuitive",
              help="对比的场景名称")
@click.option("--strategies", "-t",
              default="greedy,conservative,shortest_path",
              help="要比较的策略列表，用逗号分隔")
@click.option("--seed", type=int, default=42, help="随机种子")
@click.option("--export-metrics", type=click.Path(), help="导出指标对比CSV路径")
@click.option("--export-report", type=click.Path(), help="导出对比报告路径")
def compare(scenario: str, strategies: str, seed: int,
            export_metrics: Optional[str], export_report: Optional[str]):
    """批量比较不同策略在同一情境下的表现"""
    network = create_sample_network()
    scenarios = get_all_scenarios()

    if scenario not in scenarios:
        click.echo(f"错误: 未知场景 '{scenario}'")
        click.echo(f"可用场景: {', '.join(scenarios.keys())}")
        sys.exit(1)

    if scenario == "counterintuitive":
        click.echo(get_counterintuitive_description())

    scn = scenarios[scenario]
    strategy_list = [s.strip() for s in strategies.split(",")]

    click.echo(f"策略对比 - 场景: {scn.name}")
    click.echo(f"对比策略: {', '.join(strategy_list)}")
    click.echo("")

    results = compare_strategies(network, scn, strategy_list, seed=seed)

    comparison = ReportGenerator.generate_comparison_report(results, scn.id)
    click.echo(comparison)

    for strategy_name, (metrics, state) in results.items():
        click.echo(f"\n--- {strategy_name} 策略详细动作摘要 ---")
        report = ReportGenerator.generate_text_report(
            metrics, state, scn.name, strategy_name,
            include_actions=True, max_actions=20
        )
        action_section = report.split("调度动作序列")[1] if "调度动作序列" in report else ""
        click.echo(action_section[:600] + "..." if len(action_section) > 600 else action_section)

    if export_metrics:
        ReportGenerator.export_metrics_csv(results, export_metrics)
        click.echo(f"\n指标对比已导出到: {export_metrics}")

    if export_report:
        Path(export_report).parent.mkdir(parents=True, exist_ok=True)
        with open(export_report, "w", encoding="utf-8") as f:
            f.write(comparison)
            for strategy_name, (metrics, state) in results.items():
                f.write("\n\n" + "=" * 80 + "\n")
                f.write(f"{strategy_name} 策略详情\n")
                f.write("=" * 80 + "\n")
                full_report = ReportGenerator.generate_text_report(
                    metrics, state, scn.name, strategy_name
                )
                f.write(full_report)
        click.echo(f"完整对比报告已导出到: {export_report}")


@cli.command()
@click.option("--export-dir", "-o", default="outputs",
              type=click.Path(file_okay=False), help="输出目录")
def batch_all(export_dir: str):
    """批量运行所有场景和策略组合，生成完整报告"""
    network = create_sample_network()
    scenarios = get_all_scenarios()
    strategies = ["greedy", "conservative", "shortest_path"]

    Path(export_dir).mkdir(parents=True, exist_ok=True)

    click.echo("开始批量模拟...")
    all_results = {}

    for scn_id, scn in scenarios.items():
        click.echo(f"\n处理场景: {scn.name} ({scn_id})")
        results = compare_strategies(network, scn, strategies, seed=42)
        all_results[scn_id] = results

        comparison = ReportGenerator.generate_comparison_report(results, scn_id)
        report_path = Path(export_dir) / f"{scn_id}_comparison.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(comparison)
        click.echo(f"  对比报告: {report_path}")

        metrics_path = Path(export_dir) / f"{scn_id}_metrics.csv"
        ReportGenerator.export_metrics_csv(results, str(metrics_path))
        click.echo(f"  指标CSV: {metrics_path}")

        for strategy_name, (metrics, state) in results.items():
            actions_path = Path(export_dir) / f"{scn_id}_{strategy_name}_actions.csv"
            ReportGenerator.export_actions_csv(state, str(actions_path))

            json_path = Path(export_dir) / f"{scn_id}_{strategy_name}_state.json"
            ReportGenerator.export_state_json(state, str(json_path))

            full_report = ReportGenerator.generate_text_report(
                metrics, state, scn.name, strategy_name
            )
            full_report_path = Path(export_dir) / f"{scn_id}_{strategy_name}_report.txt"
            with open(full_report_path, "w", encoding="utf-8") as f:
                f.write(full_report)

    click.echo(f"\n所有模拟完成，结果保存在: {export_dir}")

    summary_path = Path(export_dir) / "SUMMARY.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# 配电网保供策略模拟汇总\n\n")
        f.write("## 场景说明\n\n")
        for scn_id, scn in scenarios.items():
            f.write(f"- **{scn.name}** (`{scn_id}`): {scn.description}\n")
        f.write("\n## 策略说明\n\n")
        f.write("- **greedy**: 容量优先策略，优先选择转供容量最大的路径\n")
        f.write("- **conservative**: 保守策略，只选择容量满足安全裕度的路径\n")
        f.write("- **shortest_path**: 最短路径策略，优先选择距离最短的路径\n")
        f.write("\n## 反直觉场景\n\n")
        f.write(get_counterintuitive_description())
        f.write("\n## 输出文件\n\n")
        f.write("每个场景生成:\n")
        f.write("- `{scenario}_comparison.txt`: 策略对比报告\n")
        f.write("- `{scenario}_metrics.csv`: 所有策略指标对比\n")
        f.write("- `{scenario}_{strategy}_report.txt`: 单策略完整报告\n")
        f.write("- `{scenario}_{strategy}_actions.csv`: 调度动作日志\n")
        f.write("- `{scenario}_{strategy}_state.json`: 终态数据\n")

    click.echo(f"汇总文档: {summary_path}")


@cli.command()
def list_scenarios():
    """列出所有可用场景"""
    scenarios = get_all_scenarios()
    click.echo("可用场景:")
    for scn_id, scn in scenarios.items():
        click.echo(f"  {scn_id:15s} - {scn.name}: {scn.description}")

    click.echo("\n可用策略:")
    strategies = [
        ("greedy", "容量优先，优先选择转供容量最大的路径"),
        ("conservative", "保守策略，只选择容量满足安全裕度的路径"),
        ("shortest_path", "最短路径优先，可能选择容量不足的线路"),
    ]
    for name, desc in strategies:
        click.echo(f"  {name:15s} - {desc}")

    click.echo("\n" + get_counterintuitive_description())


@cli.command()
def demo_counterintuitive():
    """演示反直觉场景 - 最短路径vs容量优先"""
    network = create_sample_network()
    scenarios = get_all_scenarios()
    scn = scenarios["counterintuitive"]

    click.echo(get_counterintuitive_description())
    click.echo("\n" + "=" * 80)
    click.echo("演示: 反直觉转供场景")
    click.echo("=" * 80)

    strategies = ["shortest_path", "greedy", "conservative"]
    results = compare_strategies(network, scn, strategies, seed=42)

    comparison = ReportGenerator.generate_comparison_report(results, scn.id)
    click.echo(comparison)

    click.echo("\n" + "=" * 80)
    click.echo("关键发现:")
    click.echo("=" * 80)
    sp_metrics = results["shortest_path"][0]
    greedy_metrics = results["greedy"][0]

    click.echo(f"\n1. 最短路径策略:")
    click.echo(f"   - 选择了TIE2(容量3MW)，因为距离最短")
    click.echo(f"   - 二次故障次数: {sp_metrics.secondary_fault_count}")
    click.echo(f"   - 重要负荷保障率: {sp_metrics.critical_serve_rate:.1%}")
    click.echo(f"   - 未供电电量: {sp_metrics.total_unserved_energy:.2f} MWh")

    click.echo(f"\n2. 容量优先策略:")
    click.echo(f"   - 选择了TIE3(容量15MW)，虽然稍远但容量充足")
    click.echo(f"   - 二次故障次数: {greedy_metrics.secondary_fault_count}")
    click.echo(f"   - 重要负荷保障率: {greedy_metrics.critical_serve_rate:.1%}")
    click.echo(f"   - 未供电电量: {greedy_metrics.total_unserved_energy:.2f} MWh")

    if sp_metrics.secondary_fault_count > greedy_metrics.secondary_fault_count or \
       sp_metrics.total_unserved_energy > greedy_metrics.total_unserved_energy:
        click.echo("\n[OK] 验证成功: 最短路径策略表现更差，容量优先策略更稳定")
    else:
        click.echo("\n[!] 注意: 因随机性结果可能变化，建议多次运行")


if __name__ == "__main__":
    cli()
