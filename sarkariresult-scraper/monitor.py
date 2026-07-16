# ============================================================
#  monitor.py — Per-repo health/status reporter
#  Runs after every scraper run. Writes monitor/status.json
#  with: today's Action runs (success/fail/times) + today's
#  scraped file counts (total + per category).
# ============================================================

import os
import json
import glob
import requests
from datetime import datetime, timezone

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY")  # "owner/repo", auto-set by Actions
DATA_DIR = "data"


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_runs():
    """Get this repo's own Actions run history via GitHub API."""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        return []
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/runs?per_page=50"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json().get("workflow_runs", [])
    except Exception as e:
        print(f"[monitor] Error fetching runs: {e}")
        return []


def today_run_summary():
    today = get_today_str()
    runs = fetch_runs()
    today_runs = [r for r in runs if r.get("created_at", "").startswith(today)]

    success = sum(1 for r in today_runs if r.get("conclusion") == "success")
    failed = sum(1 for r in today_runs if r.get("conclusion") == "failure")
    other = len(today_runs) - success - failed

    times = sorted([r.get("created_at") for r in today_runs if r.get("created_at")])
    last_run = times[-1] if times else None

    return {
        "total_runs_today": len(today_runs),
        "success": success,
        "failed": failed,
        "other": other,
        "run_times_utc": times,
        "last_run_utc": last_run,
    }


def scraped_files_summary():
    """Count today's scraped JSON files, per category, inside data/<today>/."""
    today = get_today_str()
    base = os.path.join(DATA_DIR, today)
    result = {"total_files": 0, "by_category": {}}

    if os.path.isdir(base):
        for cat in sorted(os.listdir(base)):
            cat_path = os.path.join(base, cat)
            if os.path.isdir(cat_path):
                files = glob.glob(os.path.join(cat_path, "*.json"))
                result["by_category"][cat] = len(files)
                result["total_files"] += len(files)

    return result


def main():
    status = {
        "repo": GITHUB_REPOSITORY,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "date": get_today_str(),
        "runs": today_run_summary(),
        "scraped": scraped_files_summary(),
    }

    os.makedirs("monitor", exist_ok=True)
    with open("monitor/status.json", "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)

    print("[monitor] status.json written:")
    print(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()