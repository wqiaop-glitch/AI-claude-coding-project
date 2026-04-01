"""
review_jobs.py — 交互式投递清单生成器
流程：读取最新 CSV → 展示列表 → 用户选 Top 5 → 生成投递清单 Markdown
清单包含：推荐简历、是否需要 Cover Letter、3 条 STAR 故事建议
"""

import os
import glob
import pandas as pd
import yaml
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

console = Console()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config() -> dict:
    """加载 config.yml"""
    cfg_path = os.path.join(BASE_DIR, "config.yml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_latest_csv() -> str | None:
    """找到 outputs/ 下最新的 jobs_*.csv 文件"""
    pattern = os.path.join(BASE_DIR, "outputs", "jobs_*.csv")
    files = sorted(glob.glob(pattern), reverse=True)
    return files[0] if files else None


def display_jobs(df: pd.DataFrame):
    """在终端展示职位列表供用户选择"""
    table = Table(
        title="今日职位列表",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", width=3)
    table.add_column("Company", width=14)
    table.add_column("Title", width=34)
    table.add_column("Location", width=16)
    table.add_column("Resume", width=10)
    table.add_column("Reason", width=30)

    for i, (_, row) in enumerate(df.iterrows(), 1):
        table.add_row(
            str(i),
            str(row.get("Company", ""))[:13],
            str(row.get("Title", ""))[:33],
            str(row.get("Location", ""))[:15],
            str(row.get("ResumeID", "")),
            str(row.get("MatchReason", ""))[:29],
        )
    console.print(table)


# ── Cover Letter 判断 ────────────────────────────

# 这些关键词出现在标题/描述中时，建议写 Cover Letter
_CL_KEYWORDS = [
    "product", "marketing", "brand", "content", "communications",
    "strategy", "consulting", "program manager", "project manager",
    "growth", "operations", "design", "research",
]


def needs_cover_letter(row: pd.Series) -> tuple[bool, str]:
    """
    判断是否需要 Cover Letter
    规则：PM/MA track 或标题含软技能岗关键词 → 需要
    """
    title = str(row.get("Title", "")).lower()
    resume = str(row.get("ResumeID", "")).upper()

    # PM / MA 方向建议写 CL
    if resume in ("PM", "MA"):
        return True, f"{resume} 方向岗位，Cover Letter 能突出沟通与领导力"

    # 标题命中软技能岗关键词
    for kw in _CL_KEYWORDS:
        if kw in title:
            return True, f"标题含 \"{kw}\"，建议用 Cover Letter 体现软实力"

    return False, "技术岗，简历为主即可；如有内推可省略 CL"


# ── STAR 故事建议 ─────────────────────────────────

# 按 track 预设 STAR 故事方向
_STAR_TEMPLATES = {
    "BA": [
        "用数据分析发现业务问题并推动决策的经历（突出 SQL/Excel/BI 工具）",
        "跨部门协作、整合需求并输出可视化报告的项目",
        "独立完成端到端数据清洗→分析→演示的案例",
    ],
    "BA-v2": [
        "用数据分析发现业务问题并推动决策的经历（突出 SQL/Excel/BI 工具）",
        "跨部门协作、整合需求并输出可视化报告的项目",
        "独立完成端到端数据清洗→分析→演示的案例",
    ],
    "PM": [
        "从 0 到 1 主导一个产品功能的规划与上线经历",
        "通过用户调研/A-B 测试驱动产品优化的案例",
        "协调工程、设计、运营多方资源推进项目按时交付的经历",
    ],
    "MA": [
        "策划并执行一次营销活动/campaign 并量化效果的经历",
        "利用数据分析优化投放策略（ROI/转化率提升）的案例",
        "撰写市场调研报告或竞品分析并影响团队决策的经历",
    ],
    "default": [
        "解决一个有挑战性的技术/业务问题的经历",
        "团队协作中发挥关键作用的项目经历",
        "在有限时间/资源下高效完成任务的案例",
    ],
}


def suggest_star_stories(row: pd.Series) -> list[str]:
    """根据匹配的简历方向，返回 3 条 STAR 故事准备建议"""
    resume_id = str(row.get("ResumeID", "default"))
    return _STAR_TEMPLATES.get(resume_id, _STAR_TEMPLATES["default"])


# ── 简历文件查找 ─────────────────────────────────

def get_resume_file(resume_id: str, config: dict) -> str:
    """从 config 中查找简历文件路径"""
    profiles = config.get("resume_profiles", {})
    prof = profiles.get(resume_id, profiles.get("default", {}))
    return prof.get("file", "（未配置）")


# ── 导出投递清单 ─────────────────────────────────

def export_checklist(selected: pd.DataFrame, config: dict) -> str:
    """生成投递清单 Markdown 并保存"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = os.path.join(BASE_DIR, "outputs")
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"checklist_{date_str}.md")

    lines = [
        f"# 投递清单 — {date_str}",
        "",
        f"> 从今日 {len(selected)} 条精选职位中生成",
        "",
    ]

    for i, (_, row) in enumerate(selected.iterrows(), 1):
        company = row.get("Company", "")
        title = row.get("Title", "")
        location = row.get("Location", "")
        apply_url = row.get("ApplyURL", "")
        resume_id = str(row.get("ResumeID", "default"))
        resume_file = get_resume_file(resume_id, config)
        match_reason = row.get("MatchReason", "")

        cl_needed, cl_reason = needs_cover_letter(row)
        stars = suggest_star_stories(row)

        lines.append(f"## {i}. {company} — {title}")
        lines.append("")
        lines.append(f"- **地点**: {location}")
        lines.append(f"- **申请链接**: [{apply_url}]({apply_url})")
        lines.append(f"- **匹配原因**: {match_reason}")
        lines.append("")

        # 简历推荐
        lines.append(f"### 推荐简历")
        lines.append(f"- **简历 ID**: `{resume_id}`")
        lines.append(f"- **文件**: `{resume_file}`")
        lines.append("")

        # Cover Letter
        lines.append(f"### Cover Letter")
        cl_icon = "Yes" if cl_needed else "No"
        lines.append(f"- **是否需要**: {cl_icon}")
        lines.append(f"- **理由**: {cl_reason}")
        lines.append("")

        # STAR 故事
        lines.append(f"### 准备 3 条 STAR 故事")
        for j, story in enumerate(stars, 1):
            lines.append(f"{j}. {story}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ── 主流程 ───────────────────────────────────────

def run():
    console.print("\n[bold magenta]═══ Job Review & Checklist ═══[/bold magenta]\n")

    # 1. 找到最新 CSV
    csv_path = find_latest_csv()
    if not csv_path:
        console.print("[red]outputs/ 下没有 jobs_*.csv 文件，请先运行 rank_and_export.py[/red]")
        return

    console.print(f"[dim]读取: {csv_path}[/dim]\n")
    df = pd.read_csv(csv_path)

    if df.empty:
        console.print("[red]CSV 为空，无职位可选[/red]")
        return

    # 2. 展示列表
    display_jobs(df)

    # 3. 让用户选择 Top 5
    console.print()
    raw = Prompt.ask(
        "[bold]请输入你想投递的职位编号（最多 5 个，逗号分隔，如 1,3,5,7,12）[/bold]"
    )

    try:
        indices = [int(x.strip()) - 1 for x in raw.split(",") if x.strip()]
        indices = [i for i in indices if 0 <= i < len(df)][:5]  # 最多 5 个
    except ValueError:
        console.print("[red]输入格式错误，请用逗号分隔数字[/red]")
        return

    if not indices:
        console.print("[yellow]未选择任何职位[/yellow]")
        return

    selected = df.iloc[indices].copy()
    console.print(f"\n[green]已选 {len(selected)} 条职位，正在生成投递清单...[/green]\n")

    # 4. 加载配置、生成清单
    config = load_config()
    path = export_checklist(selected, config)

    # 5. 终端预览
    console.print(f"[bold green]投递清单已保存: {path}[/bold green]\n")

    for i, (_, row) in enumerate(selected.iterrows(), 1):
        resume_id = str(row.get("ResumeID", "default"))
        cl_needed, _ = needs_cover_letter(row)
        cl_tag = "[red]需要CL[/red]" if cl_needed else "[dim]无需CL[/dim]"
        console.print(
            f"  {i}. [bold]{row['Company']}[/bold] — {row['Title']}  "
            f"📄 {resume_id}  {cl_tag}"
        )

    console.print(f"\n[dim]用 VS Code 打开清单查看完整 STAR 建议：code {path}[/dim]\n")


if __name__ == "__main__":
    run()
