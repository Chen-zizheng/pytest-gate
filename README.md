# pytest-gate — 用例分级 / 失败重跑 / 汇总门禁

一个约 150 行的 pytest 插件，解决 CI 上的三个具体问题：

- **每次提交都跑全量？** 跑不起，也不该跑——只有 smoke 该进每次 pipeline。
- **偶发失败直接判红？** 团队会开始无视红灯。给一次重跑机会，但重跑次数必须报出来，不能悄悄吞掉。
- **「测试通过」之后呢？** 门禁要能读机器可读的汇总，失败数超过阈值时用一个独立的退出码拦下来。

```
pytest --level smoke                 # 只跑冒烟
pytest --gate-reruns 1              # 失败重跑一次，重跑次数写进汇总
pytest --gate-report gate.json      # 写机器可读的汇总
pytest --gate-max-fail 0            # 有失败就以退出码 2 结束，交给 CI 拦截
```

## 装在项目里

```bash
pip install -e /path/to/pytest-gate
pytest -p pytest_gate.plugin -q
```

也可以放进 `conftest.py`：`pytest_plugins = ["pytest_gate.plugin"]`。

## 实测（在 canfault 的 26 条用例上）

```
$ pytest -p pytest_gate.plugin --level smoke -q
22 passed, 4 deselected in 0.22s

$ pytest -p pytest_gate.plugin --gate-reruns 1 --gate-report reports/gate.json -q
collected 26 | passed 26 | failed 0 | skipped 0 | rerun 0 | 3.46s
  slowest 1.705s  tests/test_fuzz.py::test_fuzz_finds_crashes_on_virtual_bus
  slowest 1.554s  tests/test_fuzz.py::test_minimize_never_grows
26 passed in 3.46s
```

冒烟集 0.22 秒、全量 3.46 秒，差 15 倍：26 条里只有 4 条在虚拟总线上收发报文，这 4 条占了 94% 的时间。

## 四个实现决定

1. **重跑走 protocol 层整轮。** 用 `_pytest.runner.runtestprotocol` 把 setup / call / teardown 完整再跑一遍，fixture 里的临时状态（数据库连接、总线句柄）会一起重建。代价是依赖了一个下划线开头的私有 API，pytest 大版本升级时得看一眼。
2. **中间失败标成 `rerun`。** 标 failed 的终端输出是「1 failed, 1 passed」，读的人以为一半挂了；标 rerun 之后 pytest 显示「1 passed, 1 rerun」，重跑次数一眼可见。
3. **门禁用退出码 2，不用 1。** 1 是 pytest 自己的「有用例失败」，2 留给「失败数超过阈值」——CI 里可以据此区分「测试红了」和「测试红了且超出容忍度」。
4. **汇总只统计 call 阶段。** setup 失败计入 failed 但不计 slowest，否则 fixture 挂掉会把耗时榜污染成一片零。

## 已知限制

- 只支持 `smoke` / `regression` 两级，没有做任意层级或按标签组合。
- 重跑是串行的，没有和 pytest-xdist 联调过；分布式下重跑只会发生在各自 worker 内。
- 汇总里的耗时只算 call 阶段，不含 setup / teardown，所以和 `--durations` 的数字不完全一致。
