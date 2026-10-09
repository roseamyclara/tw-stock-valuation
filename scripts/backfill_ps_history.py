"""從 Git 已保存的 latest/meta 快照回補 P/S；需完整 Git 歷史。

僅還原當時保存的值及計算基礎，無資料的月份不推估。每日流程不用掃 Git，
由 build_snapshot.py 直接保存當月快照。
"""
import json
import subprocess

from ps_history import PS_HISTORY, record_snapshot
from util import ROOT, log, read_json, write_json


def main():
    shallow = subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT, text=True).strip()
    if shallow == "true":
        raise SystemExit("需要完整 Git 歷史，請先 git fetch --unshallow")
    commits = subprocess.check_output(
        ["git", "log", "--first-parent", "--reverse", "--format=%H", "HEAD", "--", "docs/data/latest.json"],
        cwd=ROOT, text=True).splitlines()
    store = read_json(PS_HISTORY, {}) or {}
    for commit in commits:
        try:
            rows = json.loads(subprocess.check_output(["git", "show", f"{commit}:docs/data/latest.json"], cwd=ROOT))
            meta = json.loads(subprocess.check_output(["git", "show", f"{commit}:docs/data/meta.json"], cwd=ROOT))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        record_snapshot(store, rows, meta.get("asOf"), meta.get("updatedAt") or "")
    write_json(PS_HISTORY, dict(sorted(store.items())))
    log(f"P/S 歷史：檢查 {len(commits)} 次快照，保存 {len(store)} 個月；{list(sorted(store))}")


if __name__ == "__main__":
    main()
