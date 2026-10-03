# Day 1：开发底座与虚拟环境

## 今天要理解什么

1. `pyproject.toml` 同时描述项目、Python 版本、依赖和质量工具配置。
2. `uv.lock` 锁定每个依赖的精确版本，使另一台电脑能复现环境。
3. `.venv` 是项目独立解释器，不会污染系统 Python 3.14。
4. `src/datapilot` 是业务包；`tests` 只放可重复执行的验收代码。
5. `create_app()` 把应用构建与启动分开，后续测试不需要真的监听端口。

## 在 PyCharm 中打开

1. 选择 **Open**，直接打开 `E:\DataPilot`，不需要再复制到另一个目录。
2. 进入 **Settings → Project → Python Interpreter**。
3. 选择 Existing environment：`E:\DataPilot\.venv\Scripts\python.exe`。
4. 打开 PyCharm Terminal，运行 `uv run pytest`。

## 推荐的阅读顺序

1. `pyproject.toml`
2. `src/datapilot/config.py`
3. `src/datapilot/api/app.py`
4. `tests/test_health.py`
5. `scripts/check_quality.py`

## 今日动手练习

在 `/health/live` 的返回值中临时加入一个 `message` 字段，再同步修改测试。运行测试
观察“先失败、再通过”的过程。练习完成后可以撤销这个临时字段。

## 今日验收命令

```powershell
uv run python --version
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run pyright src
```

