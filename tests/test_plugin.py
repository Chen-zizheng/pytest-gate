# -*- coding: utf-8 -*-
import json

INNER = """
import pytest

@pytest.mark.smoke
def test_smoke_ok():
    assert True

@pytest.mark.regression
def test_regression_ok():
    assert True

@pytest.mark.regression
def test_regression_fail():
    assert 1 == 2
"""

FLAKY = """
import os
import pytest

STATE = os.path.join(os.getcwd(), "state.txt")

@pytest.mark.smoke
def test_flaky():
    seen = int(open(STATE).read()) if os.path.exists(STATE) else 0
    open(STATE, "w").write(str(seen + 1))
    assert seen >= 1
"""


def test_level_smoke_selects_only_smoke(pytester):
    pytester.makepyfile(INNER)
    result = pytester.runpytest("-p", "pytest_gate.plugin", "--level", "smoke", "-q")
    result.assert_outcomes(passed=1, deselected=2)


def test_level_all_runs_everything(pytester):
    pytester.makepyfile(INNER)
    result = pytester.runpytest("-p", "pytest_gate.plugin", "-q")
    result.assert_outcomes(passed=2, failed=1)


def test_report_json_written(pytester):
    pytester.makepyfile(INNER)
    report = pytester.path / "gate.json"
    pytester.runpytest("-p", "pytest_gate.plugin", "--gate-report", str(report), "-q")
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["collected"] == 3
    assert payload["passed"] == 2
    assert payload["failed"] == 1
    assert payload["slowest"]


def test_rerun_turns_flaky_into_pass(pytester):
    pytester.makepyfile(FLAKY)
    result = pytester.runpytest("-p", "pytest_gate.plugin", "--gate-reruns", "2", "-q")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*1 passed, 1 rerun*"])


def test_gate_max_fail_sets_exit_code(pytester):
    pytester.makepyfile(INNER)
    result = pytester.runpytest("-p", "pytest_gate.plugin", "--gate-max-fail", "0", "-q")
    assert result.ret == 2


def test_gate_under_limit_keeps_normal_exit(pytester):
    pytester.makepyfile(INNER)
    result = pytester.runpytest("-p", "pytest_gate.plugin", "--gate-max-fail", "5", "-q")
    assert result.ret == 1  # 有失败，但没超过阈值，退出码仍是 pytest 自己的 1
