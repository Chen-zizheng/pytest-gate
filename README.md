# pytest-gate — 用例分级 / 失败重跑 / 汇总门禁

一个提供用例分级、失败重跑和 JSON 汇总门禁的 pytest 插件，核心实现见 [plugin.py](pytest_gate/plugin.py)。适用于需要按标记选择测试、记录重跑和设置失败阈值的 CI 流程。

- **按阶段选择用例**：用 `smoke` / `regression` 标记筛选测试；每个流水线运行哪一组由项目自行决定。
- **记录失败重跑**：允许配置重跑次数，并把重跑数量写进汇总；重跑通过不代表偶发失败原因已解决。
- **输出机器可读汇总**：失败报告数超过阈值时设置退出码 2，由 CI 判定任务失败；该退出码不是本插件独占。

```
pytest --level smoke                 # 只跑冒烟
pytest --gate-reruns 1              # 失败重跑一次，重跑次数写进汇总
pytest --gate-report gate.json      # 写机器可读的汇总
pytest --gate-max-fail 0            # 有失败就以退出码 2 结束，交给 CI 拦截
```

## 装在项目里

```bash
pip install -e /path/to/pytest-gate
pytest -q  # 通过 pytest11 入口自动加载，不要再加 -p 重复注册
```

要求 Python >=3.9、pytest >=7（见 [pyproject.toml](pyproject.toml)）。安装后由 pytest 自动加载插件。若禁用了插件自动加载，可显式使用 `-p pytest_gate.plugin`；未安装时还需让仓库根目录位于 `PYTHONPATH`。不要同时采用自动加载、`-p` 和 `pytest_plugins` 多种加载方式。

用 `@pytest.mark.smoke` 或 `@pytest.mark.regression` 标记用例，`--level smoke` / `--level regression` 分别按对应标记筛选；regression 不自动包含 smoke，未标记用例在指定 level 时会被排除。不传 `--level` 时不做分级过滤。

## 历史运行记录（canfault 的 26 条用例）

全量结果可核对 [canfault 门禁报告](https://github.com/Chen-zizheng/canfault/blob/main/reports/gate.json)：26 passed、0 failed、wall time 3.459 秒。原 README 记录该次环境为 WSL2 Ubuntu、Python 3.14、python-can 4.6.1、pytest 9.0.2；JSON 未保存全部环境字段。下列 smoke 的 0.22 秒仅保留自原 README，没有独立原始报告，本次未复测这两组记录。以下命令假定插件已安装并自动加载。

```
$ pytest --level smoke -q
22 passed, 4 deselected in 0.22s

$ pytest --gate-reruns 1 --gate-report reports/gate.json -q
collected 26 | passed 26 | failed 0 | skipped 0 | rerun 0 | 3.46s
  slowest 1.705s  tests/test_fuzz.py::test_fuzz_finds_crashes_on_virtual_bus
  slowest 1.554s  tests/test_fuzz.py::test_minimize_never_grows
26 passed in 3.46s
```

两次历史记录不能作为稳定的性能倍数结论。已有全量报告中的两个最慢用例分别为 1.705 秒和 1.554 秒，两者合计约占 wall time 的 94%；这不是全部 4 条回归用例的独立耗时统计。

## 四个实现决定

1. **重跑走 protocol 层。** 用 `_pytest.runner.runtestprotocol` 重新执行 setup / call / teardown；不保证 module / session scope 的 fixture 全部重建，外部数据库和文件等状态也不会自动回滚。该实现依赖 pytest 私有 API，升级版本时需要回归验证。
2. **中间失败标成 `rerun`。** 标 failed 的终端输出是「1 failed, 1 passed」，读的人以为一半挂了；标 rerun 之后 pytest 显示「1 passed, 1 rerun」，重跑次数一眼可见。
3. **超阈值设置退出码 2。** 但 pytest 原生中断也使用 2，不能只凭退出码识别门禁触发；应同时查看汇总中的失败统计。阈值是附加约束，不会把阈值以内的 pytest 原生失败改成成功。
4. **区分阶段与用例数量。** `passed`、`slowest` 和 `duration_s` 仅统计成功的 call 报告；`failed` 统计最终失败的阶段报告，包含 setup / teardown，同一用例可能贡献不止一个失败。`collected` 是分级过滤前的收集数，`wall_time_s` 是会话总耗时。

## 已知限制

- 只支持 `smoke` / `regression` 两级，没有做任意层级或按标签组合。
- 重跑是串行的，没有和 pytest-xdist 联调过；不能保证分布式汇总、重跑和报告写入正确。
- `duration_s` 及慢用例榜只含成功 call，不含失败 call、setup / teardown，因此和 `--durations` 的口径不同。

## 插件自身测试

在仓库根目录运行 `python -m pytest tests -q`。测试通过 pytester 创建临时项目并启动 pytest，需要可写的临时目录。
