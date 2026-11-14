# -*- coding: utf-8 -*-
"""插件实现。

三件事，每件都对应一个真实痛点：
1. 分级：CI 每次提交只跑 smoke，nightly 才跑全量；
2. 重跑：偶发失败直接判红会让团队开始无视红灯，所以给一次机会，但重跑次数要报出来；
3. 门禁：跑完写一份 JSON 汇总，失败数超过阈值就让 exit code 变成 2，交给 CI 判断。
"""
from __future__ import annotations

import json
import os
import time

import pytest
from _pytest.runner import runtestprotocol

LEVELS = ("smoke", "regression")
_STATE = {}


def pytest_addoption(parser):
    group = parser.getgroup("gate", "用例分级 / 重跑 / 门禁")
    group.addoption("--level", action="store", default="all", choices=("all",) + LEVELS,
                    help="只跑某一级用例（默认 all）")
    group.addoption("--gate-reruns", action="store", type=int, default=0,
                    help="失败用例最多重跑几次")
    group.addoption("--gate-report", action="store", default="",
                    help="把汇总写成 JSON 到这个路径")
    group.addoption("--gate-max-fail", action="store", type=int, default=-1,
                    help="允许的失败数上限，超过则退出码为 2（默认不启用）")


def pytest_configure(config):
    _STATE["config"] = config
    config.addinivalue_line("markers", "smoke: 冒烟用例，每次提交都跑")
    config.addinivalue_line("markers", "regression: 回归用例，nightly 跑")
    config._gate_stats = {"collected": 0, "passed": 0, "failed": 0, "skipped": 0,
                          "rerun": 0, "duration_s": 0.0, "slowest": []}
    config._gate_start = time.time()


def pytest_collection_modifyitems(config, items):
    level = config.getoption("--level")
    config._gate_stats["collected"] = len(items)
    if level == "all":
        return
    keep, drop = [], []
    for item in items:
        (keep if item.get_closest_marker(level) else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep


def pytest_runtest_protocol(item, nextitem):
    reruns = max(0, item.config.getoption("--gate-reruns"))
    for attempt in range(reruns + 1):
        reports = runtestprotocol(item, nextitem=nextitem, log=False)
        failed = any(r.failed for r in reports)
        last = attempt == reruns
        for report in reports:
            if report.failed and not last:
                # 中间失败标成 rerun，避免 CI 上出现「1 failed 1 passed」这种误导信息
                report.outcome = "rerun"
            item.ihook.pytest_runtest_logreport(report=report)
        if not failed or last:
            break
        item.config._gate_stats["rerun"] += 1
    return True


def pytest_runtest_logreport(report):
    config = _STATE.get("config")
    stats = getattr(config, "_gate_stats", None)
    if stats is None:
        return
    if report.when == "call" and report.passed:
        stats["passed"] += 1
        stats["slowest"].append((report.duration, report.nodeid))
        stats["duration_s"] += report.duration
    elif report.outcome == "rerun":
        pass
    elif report.failed:
        stats["failed"] += 1
    elif report.skipped and report.when in ("setup", "call"):
        stats["skipped"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalwriter = terminalreporter
    stats = config._gate_stats
    stats["slowest"] = [
        {"nodeid": n, "duration_s": round(d, 3)}
        for d, n in sorted(stats["slowest"], reverse=True)[:5]
    ]
    stats["wall_s"] = round(time.time() - getattr(config, "_gate_start", time.time()), 3)
    stats["exit_code"] = int(exitstatus)
    terminalwriter.write_sep("-", "gate 汇总")
    terminalwriter.write_line(
        "collected %d | passed %d | failed %d | skipped %d | rerun %d | %.2fs"
        % (stats["collected"], stats["passed"], stats["failed"], stats["skipped"],
           stats["rerun"], stats["wall_s"])
    )
    for row in stats["slowest"][:3]:
        terminalwriter.write_line("  slowest %.3fs  %s" % (row["duration_s"], row["nodeid"]))
    path = config.getoption("--gate-report")
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False, indent=2)
        terminalwriter.write_line("report -> %s" % path)


def pytest_sessionfinish(session, exitstatus):
    limit = session.config.getoption("--gate-max-fail")
    if limit >= 0 and session.config._gate_stats["failed"] > limit:
        session.exitstatus = 2
