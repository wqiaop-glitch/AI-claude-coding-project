"""
collect.py — 从 Greenhouse / Lever 公开 API 抓取职位数据
两个核心函数：
  fetch_greenhouse(board_token, company) -> list[dict]
  fetch_lever(slug, company)            -> list[dict]
返回统一格式的 job 字典列表，供 rank_and_export.py 消费
"""

import requests
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
from rich.console import Console

console = Console()

# 请求超时（秒）
TIMEOUT = 15
# User-Agent（礼貌爬虫标识）
HEADERS = {
    "User-Agent": "JobAgentDemo/1.0 (internship-tracker; educational-use)"
}


# ── 统一输出格式 ─────────────────────────────────
def _normalize(
    *,
    company: str,
    title: str,
    location: str,
    url: str,
    apply_url: str,
    posted_date: str,
    description: str,
    department: str,
    source: str,
) -> dict:
    """将各平台数据统一成相同字段的字典"""
    return {
        "company": company.strip(),
        "title": title.strip(),
        "location": location.strip(),
        "url": url.strip(),
        "apply_url": apply_url.strip(),
        "posted_date": posted_date,
        "description": description[:2000],  # 截断过长描述
        "department": department.strip(),
        "source": source,
    }


# ── Greenhouse ───────────────────────────────────
def fetch_greenhouse(board_token: str, company: str) -> list[dict]:
    """
    从 Greenhouse 公开 API 获取职位列表
    API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
    无需 API key，公开可访问
    """
    api_url = (
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
        f"?content=true"
    )
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        console.print(f"  [red]Greenhouse [{company}] 请求失败: {e}[/red]")
        return []

    jobs_raw = data.get("jobs", [])
    results = []

    for j in jobs_raw:
        # 解析发布时间：优先 updated_at，其次 first_published_at，再次 created_at
        posted = ""
        for date_field in ("updated_at", "first_published_at", "created_at"):
            raw = j.get(date_field, "")
            if raw:
                try:
                    dt = dateutil_parser.parse(raw)
                    posted = dt.strftime("%Y-%m-%d")
                    break
                except (ValueError, TypeError):
                    continue

        # 解析地点（可能有多个 office）
        offices = j.get("offices", [])
        location = ", ".join(o.get("name", "") for o in offices) if offices else ""
        loc_obj = j.get("location", {})
        if not location and loc_obj:
            location = loc_obj.get("name", "")

        # 职位详情页 URL
        job_url = j.get("absolute_url", "")

        # 部门
        departments = j.get("departments", [])
        dept = departments[0].get("name", "") if departments else ""

        # 描述（HTML 简单清理）
        content = j.get("content", "")

        results.append(_normalize(
            company=company,
            title=j.get("title", ""),
            location=location,
            url=job_url,
            apply_url=job_url,  # Greenhouse 详情页即投递页
            posted_date=posted,
            description=content,
            department=dept,
            source="greenhouse",
        ))

    console.print(
        f"  [green]Greenhouse [{company}][/green] 获取 {len(results)} 条"
    )
    return results


# ── Lever ────────────────────────────────────────
def fetch_lever(slug: str, company: str) -> list[dict]:
    """
    从 Lever 公开 API 获取职位列表
    API: https://api.lever.co/v0/postings/{slug}?mode=json
    无需 API key，公开可访问
    """
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        resp = requests.get(api_url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        console.print(f"  [red]Lever [{company}] 请求失败: {e}[/red]")
        return []

    # Lever 返回的是一个列表
    if not isinstance(data, list):
        console.print(f"  [yellow]Lever [{company}] 返回格式异常，跳过[/yellow]")
        return []

    results = []
    for j in data:
        # 发布时间：优先 createdAt（毫秒时间戳），其次 updatedAt
        posted = ""
        for ts_field in ("createdAt", "updatedAt"):
            ts = j.get(ts_field, 0)
            if ts:
                try:
                    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    posted = dt.strftime("%Y-%m-%d")
                    break
                except (ValueError, TypeError, OSError):
                    continue

        # 地点
        categories = j.get("categories", {})
        location = categories.get("location", "")
        # Lever 有时把 location 放在 categories 里
        if not location:
            location = categories.get("allLocations", [""])[0] if categories.get("allLocations") else ""

        # 部门 / 团队
        dept = categories.get("team", "")
        if not dept:
            dept = categories.get("department", "")

        # URL
        job_url = j.get("hostedUrl", "")
        apply_url = j.get("applyUrl", job_url)

        # 描述
        desc_parts = j.get("descriptionPlain", "")
        if not desc_parts:
            lists = j.get("lists", [])
            desc_parts = " ".join(
                item.get("text", "")
                for lst in lists
                for item in lst.get("content", "")
                if isinstance(item, dict)
            ) if lists else ""

        results.append(_normalize(
            company=company,
            title=j.get("text", ""),
            location=location,
            url=job_url,
            apply_url=apply_url,
            posted_date=posted,
            description=str(desc_parts),
            department=dept,
            source="lever",
        ))

    console.print(
        f"  [green]Lever [{company}][/green] 获取 {len(results)} 条"
    )
    return results


# ── 汇总入口 ─────────────────────────────────────
def collect_all(config: dict) -> list[dict]:
    """
    根据 config.yml 中的 sources 配置，逐个抓取所有公司的职位
    返回全量 job 列表（未过滤、未去重）
    """
    all_jobs = []
    sources = config.get("sources", {})

    # Greenhouse
    console.print("[bold cyan]── 抓取 Greenhouse ──[/bold cyan]")
    for src in sources.get("greenhouse", []):
        jobs = fetch_greenhouse(src["board_token"], src["company"])
        all_jobs.extend(jobs)

    # Lever
    console.print("[bold cyan]── 抓取 Lever ──[/bold cyan]")
    for src in sources.get("lever", []):
        jobs = fetch_lever(src["slug"], src["company"])
        all_jobs.extend(jobs)

    console.print(f"\n[bold]总计抓取: {len(all_jobs)} 条原始职位[/bold]")
    return all_jobs


# 单独测试
if __name__ == "__main__":
    import yaml, os

    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    jobs = collect_all(cfg)
    console.print(f"\n抓取完成，共 {len(jobs)} 条")
    if jobs:
        console.print(f"示例: {jobs[0]['company']} — {jobs[0]['title']}")
